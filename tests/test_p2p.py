# -*- coding: utf-8 -*-
"""PYaCy P2P 协议和网络层测试。

测试 p2p/protocol.py、p2p/hello.py、dht/search.py、network.py。
使用 mock 模拟 HTTP 连接。
"""

import json
import time
from typing import Any
from unittest.mock import MagicMock, patch, mock_open

import pytest

from pyacy.p2p.protocol import (
    P2PProtocol,
    P2PResponse,
    _encode_multipart,
    _generate_boundary,
)
from pyacy.p2p.hello import HelloClient, HelloResult, _parse_seedlist
from pyacy.p2p.seed import (
    PEERTYPE_JUNIOR,
    PEERTYPE_SENIOR,
    PEERTYPE_PRINCIPAL,
    Seed,
    SeedKeys,
)
from pyacy.dht.search import (
    DHTSearchClient,
    DHTSearchResult,
    DHTReference,
    _parse_search_response,
    _parse_references,
    _parse_links,
    _tokenize_query,
)
from pyacy.network import PYaCyNode, DEFAULT_SEED_URLS
from pyacy.exceptions import PYaCyConnectionError, PYaCyP2PError


# ===================================================================
# Multipart 编码
# ===================================================================


class TestMultipartEncoding:
    """multipart/form-data 编码测试。"""

    def test_generate_boundary(self) -> None:
        """边界字符串生成。"""
        b1 = _generate_boundary()
        b2 = _generate_boundary()
        assert b1.startswith("--PYaCy-")
        assert b1 != b2

    def test_encode_simple(self) -> None:
        """简单字段编码。"""
        boundary = "test-boundary"
        parts = {"key1": "value1", "key2": "value2"}
        body = _encode_multipart(parts, boundary)

        text = body.decode("utf-8")
        assert "test-boundary" in text
        assert 'name="key1"' in text
        assert "value1" in text
        assert 'name="key2"' in text
        assert "value2" in text

    def test_encode_empty(self) -> None:
        """空字段编码。"""
        body = _encode_multipart({}, "boundary")
        text = body.decode("utf-8")
        assert "--boundary--" in text

    def test_encode_unicode(self) -> None:
        """Unicode 内容编码。"""
        boundary = "test-boundary"
        parts = {"query": "你好世界"}
        body = _encode_multipart(parts, boundary)
        text = body.decode("utf-8")
        assert "你好世界" in text


# ===================================================================
# P2P 响应解析
# ===================================================================


class TestP2PResponse:
    """P2PResponse 解析测试。"""

    def test_parse_simple(self) -> None:
        """简单 key=value 解析。"""
        response = P2PResponse("message=ok\ncount=5\ntime=123")
        assert response.get("message") == "ok"
        assert response.get("count") == "5"
        assert response.get_int("count") == 5
        assert response.get_int("missing") == 0

    def test_parse_empty(self) -> None:
        """空响应。"""
        response = P2PResponse("")
        assert len(response.data) == 0

    def test_parse_multiline_values(self) -> None:
        """多行值。"""
        text = "key=value1\nseedlist=seed0=abc\\nseed1=def"
        response = P2PResponse(text)
        assert response.get("key") == "value1"

    def test_get_default(self) -> None:
        """默认值。"""
        response = P2PResponse("a=1")
        assert response.get("b", "default") == "default"

    def test_get_int_invalid(self) -> None:
        """非整数 int 获取。"""
        response = P2PResponse("value=not_a_number")
        assert response.get_int("value") == 0


# ===================================================================
# P2P 协议
# ===================================================================


class TestP2PProtocol:
    """P2PProtocol 测试。"""

    def test_init(self) -> None:
        """初始化。"""
        proto = P2PProtocol(timeout=60, network_name="testnet")
        assert proto.timeout == 60
        assert proto.network_name == "testnet"

    def test_basic_request_parts(self) -> None:
        """基本请求字段构建。"""
        proto = P2PProtocol()
        parts = proto.basic_request_parts("myhash123", salt="testsalt")
        assert parts["iam"] == "myhash123"
        assert parts["key"] == "testsalt"
        assert "mytime" in parts
        assert "myUTC" in parts
        assert parts["network.unit.name"] == "freeworld"

    def test_basic_request_parts_with_target(self) -> None:
        """带目标哈希的基本请求字段。"""
        proto = P2PProtocol()
        parts = proto.basic_request_parts("myhash", target_hash="targethash")
        assert parts["youare"] == "targethash"

    def test_basic_request_parts_auto_salt(self) -> None:
        """自动生成 salt。"""
        proto = P2PProtocol()
        parts = proto.basic_request_parts("myhash")
        assert len(parts["key"]) == 16

    @patch("pyacy.p2p.protocol.HTTPConnection")
    def test_post_multipart_success(self, mock_conn_class: Any) -> None:
        """成功的 POST 请求。"""
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"message=ok\nyourip=1.2.3.4"
        mock_conn.getresponse.return_value = mock_response
        mock_conn_class.return_value = mock_conn

        proto = P2PProtocol()
        response = proto.post_multipart("http://peer:8090/yacy/hello.html", {"key": "val"})
        assert response.get("message") == "ok"
        assert response.get("yourip") == "1.2.3.4"

    @patch("pyacy.p2p.protocol.HTTPConnection")
    def test_post_multipart_error(self, mock_conn_class: Any) -> None:
        """POST 请求 HTTP 错误。"""
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.read.return_value = b"Internal Error"
        mock_conn.getresponse.return_value = mock_response
        mock_conn_class.return_value = mock_conn

        proto = P2PProtocol()
        with pytest.raises(PYaCyP2PError):
            proto.post_multipart("http://peer:8090/yacy/test.html", {})

    @patch("pyacy.p2p.protocol.HTTPConnection")
    def test_post_multipart_connection_error(self, mock_conn_class: Any) -> None:
        """连接失败。"""
        mock_conn_class.side_effect = ConnectionRefusedError("Connection refused")

        proto = P2PProtocol()
        with pytest.raises(PYaCyConnectionError):
            proto.post_multipart("http://peer:8090/yacy/test.html", {})


# ===================================================================
# Hello 协议
# ===================================================================


class TestHelloClient:
    """HelloClient 测试。"""

    def test_hello_result_success(self) -> None:
        """成功响应。"""
        response = P2PResponse(
            "message=ok 128\n"
            "yourip=1.2.3.4\n"
            "yourtype=junior\n"
            "seedlist=seed0=z|eJxLSU0sSVQoyUhU0lEITk3JyM9LBQBcDAcP\n"
        )
        result = HelloResult.from_response(response)
        assert result.success
        assert result.your_ip == "1.2.3.4"
        assert result.your_type == PEERTYPE_JUNIOR
        assert result.is_junior

    def test_hello_result_senior(self) -> None:
        """Senior 判定。"""
        response = P2PResponse(
            "message=ok 256\n"
            "yourip=10.0.0.1\n"
            "yourtype=senior\n"
        )
        result = HelloResult.from_response(response)
        assert result.success
        assert result.your_type == PEERTYPE_SENIOR
        assert result.is_senior

    def test_hello_result_failure(self) -> None:
        """失败响应。"""
        response = P2PResponse("message=cannot resolve your IP")
        result = HelloResult.from_response(response)
        assert not result.success

    def test_parse_seedlist_simple(self) -> None:
        """解析简单种子列表。"""
        # 创建一个有效种子字符串
        seed_str = Seed.create_junior("test-peer").to_seed_string()
        seedlist = f"seed0={seed_str}"

        seeds = _parse_seedlist(seedlist)
        assert len(seeds) == 1
        assert seeds[0].name == "test-peer"

    def test_parse_seedlist_empty(self) -> None:
        """空种子列表。"""
        assert _parse_seedlist("") == []

    def test_parse_seedlist_multiple(self) -> None:
        """多个种子的列表。"""
        s1 = Seed.create_junior("peer1").to_seed_string()
        s2 = Seed.create_junior("peer2").to_seed_string()
        seedlist = f"seed0={s1}\nseed1={s2}"
        seeds = _parse_seedlist(seedlist)
        assert len(seeds) == 2


# ===================================================================
# DHT 搜索
# ===================================================================


class TestDHTSearch:
    """DHTSearchClient 测试。"""

    def test_tokenize_query(self) -> None:
        """查询分词。"""
        assert _tokenize_query("hello world") == ["hello", "world"]
        assert _tokenize_query("  one   two  ") == ["one", "two"]
        assert _tokenize_query("") == []

    def test_parse_references_simple(self) -> None:
        """解析简单引用。"""
        ref_str = "{urlhash1 wordhash1 http://example.com wordhash2}"
        refs = _parse_references(ref_str)
        assert len(refs) >= 1
        assert refs[0].url_hash == "urlhash1"

    def test_parse_references_empty(self) -> None:
        """空引用。"""
        assert _parse_references("") == []
        assert _parse_references("  ") == []

    def test_parse_links(self) -> None:
        """解析链接。"""
        links_str = "http://example.com\nhttp://test.org"
        links = _parse_links(links_str)
        assert links == ["http://example.com", "http://test.org"]

    def test_parse_links_empty(self) -> None:
        """空链接。"""
        assert _parse_links("") == []

    def test_parse_search_response(self) -> None:
        """完整的搜索响应解析。

        注意：P2P 响应按行解析为 key=value 格式，多行值需要
        用特殊方式处理。此测试验证单行 links 值的场景。
        """
        response = P2PResponse(
            "searchtime=150\n"
            "joincount=3\n"
            "linkcount=2\n"
            "references={hash1 word1 http://ex.com}\n"
            "links=http://example.com&sep=http://test.org\n"
        )
        result = _parse_search_response(response)
        assert result.success
        assert result.search_time_ms == 150
        assert result.join_count == 3
        assert result.link_count == 2
        assert len(result.links) == 1  # 单行 links 值（按换行分隔）

    def test_dht_search_result_empty(self) -> None:
        """空搜索结果。"""
        result = DHTSearchResult()
        assert not result.success
        assert result.total_results == 0

    def test_dht_reference_model(self) -> None:
        """DHTReference 模型。"""
        ref = DHTReference(
            url_hash="testhash1234",
            word_hash="wordhash123",
            url="http://example.com",
            ranking=0.85,
        )
        assert ref.url_hash == "testhash1234"
        assert ref.url == "http://example.com"


# ===================================================================
# PYaCyNode 网络管理
# ===================================================================


class TestPYaCyNode:
    """PYaCyNode 测试。"""

    def test_create_node(self) -> None:
        """创建节点。"""
        node = PYaCyNode(name="test-node")
        assert node.name == "test-node"
        assert len(node.hash) == 12
        assert node.peer_count == 0
        assert not node.is_bootstrapped
        assert node.my_seed.is_junior()

    def test_create_node_default_name(self) -> None:
        """默认名称。"""
        node = PYaCyNode()
        assert len(node.name) > 0

    def test_get_peer_stats_initial(self) -> None:
        """初始统计。"""
        node = PYaCyNode()
        stats = node.get_peer_stats()
        assert stats["total_peers"] == 0
        assert stats["senior_peers"] == 0
        assert stats["is_bootstrapped"] is False
        assert stats["my_name"] == node.name

    def test_add_peer(self) -> None:
        """手动添加节点。"""
        node = PYaCyNode()
        seed_str = Seed.create_junior("remote-peer").to_seed_string()
        seed = node.add_peer("http://peer:8090", seed_str)
        assert seed is not None
        assert seed.name == "remote-peer"
        assert node.peer_count == 1

    def test_add_peer_duplicate(self) -> None:
        """重复添加同一节点不应增加计数。"""
        node = PYaCyNode()
        seed_str = Seed.create_junior("remote-peer").to_seed_string()
        node.add_peer("http://peer:8090", seed_str)
        node.add_peer("http://peer:8090", seed_str)
        assert node.peer_count == 1

    def test_add_peer_invalid(self) -> None:
        """无效种子。"""
        node = PYaCyNode()
        result = node.add_peer("http://peer:8090", "invalid_seed_string")
        assert result is None

    def test_remove_peer(self) -> None:
        """移除节点。"""
        node = PYaCyNode()
        seed_str = Seed.create_junior("remote-peer").to_seed_string()
        seed = node.add_peer("http://peer:8090", seed_str)
        assert seed is not None

        removed = node.remove_peer(seed.hash)
        assert removed
        assert node.peer_count == 0

    def test_remove_nonexistent(self) -> None:
        """移除不存在的节点。"""
        node = PYaCyNode()
        assert not node.remove_peer("nonexistent")

    def test_get_peer(self) -> None:
        """按哈希获取节点。"""
        node = PYaCyNode()
        seed_str = Seed.create_junior("peer1").to_seed_string()
        seed = node.add_peer("http://p1:8090", seed_str)
        assert seed is not None

        found = node.get_peer(seed.hash)
        assert found is not None
        assert found == seed

        assert node.get_peer("nonexistent") is None

    def test_get_senior_peers_empty(self) -> None:
        """空 Senior 列表。"""
        node = PYaCyNode()
        assert node.get_senior_peers() == []

    def test_get_senior_peers_with_data(self) -> None:
        """带 Senior 节点。"""
        node = PYaCyNode()
        # 添加一个 senior 节点
        senior_dna = {
            SeedKeys.HASH: "senior001",
            SeedKeys.PEERTYPE: PEERTYPE_SENIOR,
            SeedKeys.IP: "10.0.0.1",
            SeedKeys.PORT: "8090",
            SeedKeys.NAME: "Senior1",
        }
        node._peers["senior001"] = Seed(senior_dna)
        assert node.senior_count == 1
        assert len(node.get_senior_peers()) == 1

    def test_get_peer_stats(self) -> None:
        """节点统计。"""
        node = PYaCyNode()

        # 添加各类节点
        senior = Seed({
            SeedKeys.HASH: "senior01",
            SeedKeys.PEERTYPE: PEERTYPE_SENIOR,
            SeedKeys.IP: "10.0.0.1",
            SeedKeys.PORT: "8090",
            SeedKeys.NAME: "Senior1",
        })
        junior = Seed({
            SeedKeys.HASH: "junior01",
            SeedKeys.PEERTYPE: PEERTYPE_JUNIOR,
            SeedKeys.NAME: "Junior1",
        })
        principal = Seed({
            SeedKeys.HASH: "prin01",
            SeedKeys.PEERTYPE: PEERTYPE_PRINCIPAL,
            SeedKeys.IP: "10.0.0.3",
            SeedKeys.PORT: "8090",
            SeedKeys.NAME: "Principal1",
        })
        node._peers["senior01"] = senior
        node._peers["junior01"] = junior
        node._peers["prin01"] = principal

        stats = node.get_peer_stats()
        assert stats["total_peers"] == 3
        assert stats["senior_peers"] == 2  # senior + principal
        assert stats["principal_peers"] == 1
        assert "junior" in stats["type_distribution"]

    def test_context_manager(self) -> None:
        """上下文管理器。"""
        with PYaCyNode() as node:
            node.add_peer(
                "http://p:8090",
                Seed.create_junior("test").to_seed_string(),
            )
            assert node.peer_count == 1
        # 退出后已清理
        assert node.peer_count == 0

    def test_search_without_bootstrap(self) -> None:
        """未引导时搜索应报错。"""
        node = PYaCyNode()
        with pytest.raises(PYaCyP2PError, match="无可用于搜索"):
            node.search("test")

    def test_close(self) -> None:
        """关闭节点。"""
        node = PYaCyNode()
        node.add_peer(
            "http://p:8090",
            Seed.create_junior("test").to_seed_string(),
        )
        node._is_bootstrapped = True
        node.close()
        assert node.peer_count == 0
        assert not node.is_bootstrapped
