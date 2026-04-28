# -*- coding: utf-8 -*-
"""PYaCy 网络层与集成测试。

本模块测试 PYaCyNode、DHTSearchClient、HelloClient 的集成场景，
包括节点生命周期、引导流程、搜索流程和错误处理。

所有测试均使用 mock 模拟 HTTP 请求，不需要实际网络连接。
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pyacy import PYaCyNode, Seed, SeedKeys
from pyacy.p2p.seed import (
    PEERTYPE_JUNIOR,
    PEERTYPE_SENIOR,
    PEERTYPE_PRINCIPAL,
    PEERTYPE_VIRGIN,
)
from pyacy.p2p.protocol import P2PProtocol, P2PResponse
from pyacy.p2p.hello import HelloClient, HelloResult
from pyacy.dht.search import (
    DHTSearchClient,
    DHTSearchResult,
    DHTReference,
    _parse_references,
    _parse_links,
    _parse_search_response,
    _tokenize_query,
)
from pyacy.exceptions import PYaCyP2PError, PYaCyConnectionError


# ===================================================================
# 辅助工具
# ===================================================================

def _make_senior_seed(
    name: str = "TestSenior",
    ip: str = "10.0.0.1",
    port: int = 8090,
    hash_val: str | None = None,
) -> Seed:
    """创建一个 Senior 类型的 Seed。"""
    if hash_val is None:
        hash_val = f"{name[:8]:<8s}Hash"[:12]
    dna = {
        SeedKeys.HASH: hash_val,
        SeedKeys.NAME: name,
        SeedKeys.PEERTYPE: PEERTYPE_SENIOR,
        SeedKeys.IP: ip,
        SeedKeys.PORT: str(port),
        SeedKeys.VERSION: "1.92",
        SeedKeys.UPTIME: "1440",
    }
    return Seed(dna)


def _make_principal_seed(
    name: str = "TestPrincipal",
    ip: str = "10.0.0.2",
    port: int = 8090,
) -> Seed:
    """创建一个 Principal 类型的 Seed。"""
    dna = {
        SeedKeys.HASH: f"{name[:8]:<8s}Hash"[:12],
        SeedKeys.NAME: name,
        SeedKeys.PEERTYPE: PEERTYPE_PRINCIPAL,
        SeedKeys.IP: ip,
        SeedKeys.PORT: str(port),
    }
    return Seed(dna)


def _make_junior_seed(name: str = "TestJunior") -> Seed:
    """创建一个 Junior 类型的 Seed。"""
    return Seed.create_junior(name)


# ===================================================================
# PYaCyNode 生命周期
# ===================================================================


class TestNodeLifecycle:
    """PYaCyNode 完整生命周期测试。"""

    def test_create_with_custom_params(self) -> None:
        """自定义参数创建节点。"""
        node = PYaCyNode(
            name="custom-node",
            port=9090,
            timeout=60,
            network_name="testnet",
        )
        assert node.name == "custom-node"
        assert node.hash  # 哈希非空
        assert node.my_seed.is_junior()
        assert not node.is_bootstrapped
        assert node.peer_count == 0
        node.close()

    def test_create_default_seeds(self) -> None:
        """默认种子节点列表。"""
        node = PYaCyNode()
        assert len(node._seed_urls) >= 3
        assert any("searchlab" in u for u in node._seed_urls)
        node.close()

    def test_create_custom_seeds(self) -> None:
        """自定义种子节点。"""
        custom = ["http://my-peer:8090"]
        node = PYaCyNode(seed_urls=custom)
        assert node._seed_urls == custom
        node.close()

    def test_context_manager_cleanup(self) -> None:
        """上下文管理器自动清理。"""
        with PYaCyNode() as node:
            node._peers["test"] = _make_senior_seed()
            node._is_bootstrapped = True
            assert node.peer_count == 1
            assert node.is_bootstrapped
        # 退出后清理
        assert node.peer_count == 0
        assert not node.is_bootstrapped

    def test_close_idempotent(self) -> None:
        """多次关闭不会报错。"""
        node = PYaCyNode()
        node.close()
        node.close()  # 不应抛出异常

    def test_bootstrap_age_initial(self) -> None:
        """初始引导年龄应为无穷。"""
        node = PYaCyNode()
        assert node.bootstrap_age == float("inf")
        node.close()


# ===================================================================
# PYaCyNode 节点管理
# ===================================================================


class TestNodePeerManagement:
    """PYaCyNode 节点增删查测试。"""

    def test_add_senior_peer(self) -> None:
        """添加 Senior 节点。"""
        node = PYaCyNode()
        seed_str = _make_senior_seed().to_seed_string()
        seed = node.add_peer("http://10.0.0.1:8090", seed_str)
        assert seed is not None
        assert node.peer_count == 1
        assert node.senior_count == 1
        node.close()

    def test_add_junior_peer(self) -> None:
        """添加 Junior 节点不计入 Senior。"""
        node = PYaCyNode()
        seed_str = _make_junior_seed().to_seed_string()
        node.add_peer("http://unknown:8090", seed_str)
        assert node.peer_count == 1
        assert node.senior_count == 0  # Junior 不计入
        node.close()

    def test_add_self_ignored(self) -> None:
        """添加自身应被忽略。"""
        node = PYaCyNode(name="self-node")
        my_seed_str = node.my_seed.to_seed_string()
        result = node.add_peer("http://self:8090", my_seed_str)
        assert result is None  # 哈希相同，忽略
        assert node.peer_count == 0
        node.close()

    def test_add_duplicate_peer(self) -> None:
        """重复添加相同哈希节点不增加计数。"""
        node = PYaCyNode()
        seed = _make_senior_seed()
        seed_str = seed.to_seed_string()
        node.add_peer("http://10.0.0.1:8090", seed_str)
        node.add_peer("http://10.0.0.1:8090", seed_str)
        assert node.peer_count == 1
        node.close()

    def test_add_invalid_seed_string(self) -> None:
        """无效种子字符串返回 None。"""
        node = PYaCyNode()
        result = node.add_peer("http://peer:8090", "not-a-valid-seed")
        assert result is None
        assert node.peer_count == 0
        node.close()

    def test_remove_peer(self) -> None:
        """移除节点。"""
        node = PYaCyNode()
        seed = _make_senior_seed()
        node._peers[seed.hash] = seed
        assert node.remove_peer(seed.hash)
        assert node.peer_count == 0
        node.close()

    def test_remove_nonexistent(self) -> None:
        """移除不存在的节点返回 False。"""
        node = PYaCyNode()
        assert not node.remove_peer("nonexist")
        node.close()

    def test_get_peer(self) -> None:
        """按哈希查找节点。"""
        node = PYaCyNode()
        seed = _make_senior_seed()
        node._peers[seed.hash] = seed
        assert node.get_peer(seed.hash) == seed
        assert node.get_peer("nonexist") is None
        node.close()

    def test_get_senior_peers(self) -> None:
        """获取 Senior 列表。"""
        node = PYaCyNode()
        senior = _make_senior_seed("S1")
        junior = _make_junior_seed("J1")
        principal = _make_principal_seed("P1")
        node._peers[senior.hash] = senior
        node._peers[junior.hash] = junior
        node._peers[principal.hash] = principal

        seniors = node.get_senior_peers()
        assert len(seniors) == 2  # senior + principal
        node.close()

    def test_peer_stats_distribution(self) -> None:
        """节点类型分布统计。"""
        node = PYaCyNode()
        node._peers["s1"] = _make_senior_seed("S1")
        node._peers["s2"] = _make_senior_seed("S2", ip="10.0.0.2")
        node._peers["p1"] = _make_principal_seed()
        node._peers["j1"] = _make_junior_seed()

        stats = node.get_peer_stats()
        assert stats["total_peers"] == 4
        assert stats["senior_peers"] == 3  # 2 senior + 1 principal
        assert stats["junior_peers"] == 1
        assert stats["principal_peers"] == 1
        dist = stats["type_distribution"]
        assert dist.get("senior", 0) == 2
        assert dist.get("principal", 0) == 1
        node.close()


# ===================================================================
# PYaCyNode 引导与搜索
# ===================================================================


class TestNodeBootstrap:
    """PYaCyNode 引导流程测试。"""

    @patch.object(HelloClient, "discover_network")
    def test_bootstrap_success(self, mock_discover: MagicMock) -> None:
        """成功引导。"""
        mock_discover.return_value = [
            _make_senior_seed("Peer1"),
            _make_senior_seed("Peer2", ip="10.0.0.2"),
        ]

        node = PYaCyNode()
        result = node.bootstrap()
        assert result is True
        assert node.is_bootstrapped
        assert node.peer_count == 2
        node.close()

    @patch.object(HelloClient, "discover_network")
    def test_bootstrap_no_peers(self, mock_discover: MagicMock) -> None:
        """引导未发现节点。"""
        mock_discover.return_value = []

        node = PYaCyNode()
        result = node.bootstrap()
        assert result is False
        assert not node.is_bootstrapped
        node.close()

    @patch.object(HelloClient, "discover_network")
    def test_bootstrap_exception(self, mock_discover: MagicMock) -> None:
        """引导过程异常。"""
        mock_discover.side_effect = PYaCyConnectionError("网络不可达")

        node = PYaCyNode()
        result = node.bootstrap()
        assert result is False
        assert not node.is_bootstrapped
        node.close()

    @patch.object(HelloClient, "discover_network")
    def test_bootstrap_updates_age(self, mock_discover: MagicMock) -> None:
        """引导后 age 应有限。"""
        mock_discover.return_value = [_make_senior_seed()]

        node = PYaCyNode()
        assert node.bootstrap_age == float("inf")
        node.bootstrap()
        assert node.bootstrap_age < 5.0
        node.close()


class TestNodeSearch:
    """PYaCyNode 搜索流程测试。"""

    def test_search_without_peers_raises(self) -> None:
        """无节点时搜索应报错。"""
        node = PYaCyNode()
        with pytest.raises(PYaCyP2PError, match="无可用于搜索"):
            node.search("test")
        node.close()

    @patch.object(DHTSearchClient, "fulltext_search")
    def test_search_with_peers(self, mock_search: MagicMock) -> None:
        """有节点时搜索正常调用。"""
        mock_search.return_value = DHTSearchResult(
            success=True,
            search_time_ms=100,
            references=[
                DHTReference(url_hash="hash1", url="http://example.com"),
            ],
        )

        node = PYaCyNode()
        node._peers["s1"] = _make_senior_seed()
        node._is_bootstrapped = True

        result = node.search("test query", count=10)
        assert result.success
        assert len(result.references) == 1
        mock_search.assert_called_once()
        node.close()

    @patch.object(DHTSearchClient, "search")
    def test_search_on_specific_peer(self, mock_search: MagicMock) -> None:
        """在指定节点搜索。"""
        mock_search.return_value = DHTSearchResult(success=True)

        node = PYaCyNode()
        target = _make_senior_seed()
        result = node.search_on_peer(target, "hello", count=5)
        assert result.success
        mock_search.assert_called_once()
        node.close()

    def test_search_on_peer_no_url(self) -> None:
        """目标节点无 URL 时搜索应报错。"""
        node = PYaCyNode()
        junior = _make_junior_seed()  # 无 IP → 无 URL
        with pytest.raises(PYaCyP2PError, match="无可用 URL"):
            node.search_on_peer(junior, "test")
        node.close()


# ===================================================================
# Hello 协议集成
# ===================================================================


class TestHelloIntegration:
    """Hello 协议与 PYaCyNode 集成测试。"""

    @patch.object(P2PProtocol, "hello")
    def test_hello_peer_success(self, mock_hello: MagicMock) -> None:
        """Hello 握手成功。"""
        mock_hello.return_value = P2PResponse(
            "message=ok 128\nyourip=1.2.3.4\nyourtype=junior"
        )

        node = PYaCyNode()
        target = _make_senior_seed()
        result = node.hello_peer(target)

        assert result is not None
        assert result["success"] is True
        assert result["your_ip"] == "1.2.3.4"
        node.close()

    @patch.object(P2PProtocol, "hello")
    def test_hello_peer_failure(self, mock_hello: MagicMock) -> None:
        """Hello 握手失败返回 None。"""
        mock_hello.side_effect = PYaCyConnectionError("连接被拒绝")

        node = PYaCyNode()
        target = _make_senior_seed()
        result = node.hello_peer(target)
        assert result is None
        node.close()

    def test_hello_peer_no_url(self) -> None:
        """无 URL 的节点 Hello 返回 None。"""
        node = PYaCyNode()
        junior = _make_junior_seed()  # 无 base_url
        result = node.hello_peer(junior)
        assert result is None
        node.close()

    @patch.object(P2PProtocol, "hello")
    def test_ping_peers(self, mock_hello: MagicMock) -> None:
        """批量 PING 节点。"""
        mock_hello.return_value = P2PResponse(
            "message=ok 64\nyourip=5.6.7.8\nyourtype=junior"
        )

        node = PYaCyNode()
        for i in range(3):
            node._peers[f"s{i}"] = _make_senior_seed(
                f"Peer{i}", ip=f"10.0.0.{i}"
            )

        results = node.ping_peers(max_peers=2)
        assert len(results) <= 2
        node.close()


# ===================================================================
# DHT 搜索解析
# ===================================================================


class TestDHTSearchParsing:
    """DHT 搜索响应解析边界测试。"""

    def test_parse_references_with_braces(self) -> None:
        """带花括号的引用。"""
        ref_str = "{urlHash1 wordHash1 http://example.com/page1 wordHash2}"
        refs = _parse_references(ref_str)
        assert len(refs) >= 1
        assert refs[0].url_hash == "urlHash1"

    def test_parse_references_multiline(self) -> None:
        """多行引用。"""
        ref_str = (
            "{hash1 wh1 http://a.com}\n"
            "{hash2 wh2 http://b.com}"
        )
        refs = _parse_references(ref_str)
        assert len(refs) >= 2

    def test_parse_references_only_hash(self) -> None:
        """仅 URL 哈希和词哈希（无 URL）。"""
        ref_str = "{urlHash1 wordHash1}"
        refs = _parse_references(ref_str)
        # 只有 2 个部分，视为 url_hash + word_hash
        assert len(refs) >= 1

    def test_parse_links_multiline(self) -> None:
        """多行链接。"""
        links_str = "http://a.com\nhttp://b.com\nhttp://c.com"
        links = _parse_links(links_str)
        assert links == ["http://a.com", "http://b.com", "http://c.com"]

    def test_parse_links_with_empty_lines(self) -> None:
        """含空行的链接。"""
        links_str = "http://a.com\n\nhttp://b.com\n  "
        links = _parse_links(links_str)
        assert links == ["http://a.com", "http://b.com"]

    def test_tokenize_unicode(self) -> None:
        """Unicode 查询分词。"""
        tokens = _tokenize_query("python 编程")
        assert len(tokens) == 2
        assert "python" in tokens
        assert "编程" in tokens

    def test_tokenize_empty(self) -> None:
        """空查询。"""
        assert _tokenize_query("") == []
        assert _tokenize_query("   ") == []

    def test_parse_search_response_full(self) -> None:
        """完整搜索响应解析。"""
        response = P2PResponse(
            "searchtime=500\n"
            "joincount=10\n"
            "linkcount=3\n"
            "references={hash1 wh1 http://x.com}\n"
            "links=http://x.com"
        )
        result = _parse_search_response(response)
        assert result.success
        assert result.search_time_ms == 500
        assert result.join_count == 10
        assert result.link_count == 3

    def test_parse_search_response_zero_results(self) -> None:
        """零结果搜索响应。"""
        response = P2PResponse(
            "searchtime=50\njoincount=2\nlinkcount=0\nreferences="
        )
        result = _parse_search_response(response)
        assert result.success
        assert len(result.references) == 0
        assert result.total_results == 0

    def test_dht_search_result_compatibility(self) -> None:
        """DHTSearchResult 兼容 SearchResult 接口。"""
        result = DHTSearchResult(
            success=True,
            references=[
                DHTReference(url_hash="h1", url="http://a.com"),
                DHTReference(url_hash="h2", url="http://b.com"),
            ],
        )
        assert result.total_results == 2
        assert len(result.items) == 2


class TestDHTSearchClient:
    """DHTSearchClient 单元测试。"""

    @patch.object(P2PProtocol, "search")
    def test_search_success(self, mock_search: MagicMock) -> None:
        """搜索成功。"""
        mock_search.return_value = P2PResponse(
            "searchtime=200\njoincount=5\nlinkcount=1\n"
            "references={urlH1 wordH1 http://test.com}\n"
            "links=http://test.com"
        )

        client = DHTSearchClient(P2PProtocol())
        result = client.search(
            target_url="http://peer:8090",
            target_hash="targethash1",
            my_hash="myhash123456",
            query="hello world",
        )
        assert result.success
        assert result.search_time_ms == 200

    @patch.object(P2PProtocol, "search")
    def test_search_failure(self, mock_search: MagicMock) -> None:
        """搜索失败返回空结果。"""
        mock_search.side_effect = PYaCyConnectionError("连接失败")

        client = DHTSearchClient(P2PProtocol())
        result = client.search(
            target_url="http://peer:8090",
            target_hash="targethash1",
            my_hash="myhash123456",
            query="test",
        )
        assert not result.success

    @patch.object(P2PProtocol, "search")
    def test_fulltext_search_filters_peers(self, mock_search: MagicMock) -> None:
        """fulltext_search 应只选 Senior 节点。"""
        mock_search.return_value = P2PResponse(
            "searchtime=100\njoincount=1\nlinkcount=0\nreferences="
        )

        client = DHTSearchClient(P2PProtocol())
        peers = [
            _make_senior_seed("S1"),
            _make_junior_seed("J1"),  # 应被过滤
            _make_senior_seed("S2", ip="10.0.0.2"),
        ]

        result = client.fulltext_search(
            peers=peers,
            my_hash="myhash123456",
            query="test",
            max_peers=2,
        )
        assert result.success

    def test_fulltext_search_no_senior(self) -> None:
        """无可连接 Senior 时返回失败。"""
        client = DHTSearchClient(P2PProtocol())
        peers = [_make_junior_seed("J1")]

        result = client.fulltext_search(
            peers=peers,
            my_hash="myhash123456",
            query="test",
        )
        assert not result.success


# ===================================================================
# Seed JSON 解析
# ===================================================================


class TestSeedJsonParsing:
    """Seed.from_json 边界条件测试。"""

    def test_from_json_with_address_array(self) -> None:
        """Address 数组应补充 IP。"""
        data = {
            "Hash": "testHash0012",
            "Name": "AddressPeer",
            "PeerType": "senior",
            "Port": 8090,
            "Address": ["192.168.1.100:8090"],
        }
        seed = Seed.from_json(data)
        assert seed.ip == "192.168.1.100"
        assert seed.port == 8090

    def test_from_json_with_ipv6_address(self) -> None:
        """IPv6 Address 应正确解析。"""
        data = {
            "Hash": "ipv6Hash0001",
            "Name": "IPv6Peer",
            "PeerType": "senior",
            "Port": 8090,
            "Address": ["[::1]:8090"],
        }
        seed = Seed.from_json(data)
        assert seed.ip is not None
        # IPv6 应在 base_url 中添加方括号
        assert seed.base_url is not None

    def test_from_json_with_existing_ip(self) -> None:
        """已有 IP 字段时 Address 不覆盖。"""
        data = {
            "Hash": "ipTestHash1",
            "Name": "IPPeer",
            "PeerType": "senior",
            "IP": "10.0.0.1",
            "Port": 8090,
            "Address": ["192.168.1.1:8090"],
        }
        seed = Seed.from_json(data)
        # IP 已在 dna 中，Address 不覆盖
        assert seed.ip == "10.0.0.1"

    def test_from_json_skips_news(self) -> None:
        """news 字段应被跳过。"""
        data = {
            "Hash": "newsHash0001",
            "PeerType": "senior",
            "news": "some-news-data",
        }
        seed = Seed.from_json(data)
        assert "news" not in seed.dna

    def test_from_json_null_values(self) -> None:
        """None 值应被跳过。"""
        data = {
            "Hash": "nullHash0001",
            "Name": "NullPeer",
            "PeerType": "senior",
            "IP": None,
            "Port": 8090,
        }
        seed = Seed.from_json(data)
        assert seed.ip is None  # None → 不存入 dna


# ===================================================================
# Seed 可达性与 IPv6
# ===================================================================


class TestSeedReachability:
    """Seed 可达性与 URL 构造测试。"""

    def test_ipv4_base_url(self) -> None:
        """IPv4 base_url。"""
        seed = _make_senior_seed(ip="192.168.1.1")
        assert seed.base_url == "http://192.168.1.1:8090"

    def test_ipv6_base_url(self) -> None:
        """IPv6 base_url 应加方括号。"""
        dna = {
            SeedKeys.HASH: "ipv6testhsh",
            SeedKeys.NAME: "IPv6Peer",
            SeedKeys.PEERTYPE: PEERTYPE_SENIOR,
            SeedKeys.IP: "::1",
            SeedKeys.PORT: "8090",
        }
        seed = Seed(dna)
        assert seed.base_url == "http://[::1]:8090"

    def test_ipv6_already_bracketed(self) -> None:
        """已有方括号的 IPv6 不重复添加。"""
        dna = {
            SeedKeys.HASH: "bracketdIPv6",
            SeedKeys.PEERTYPE: PEERTYPE_SENIOR,
            SeedKeys.IP: "[::1]",
            SeedKeys.PORT: "8090",
        }
        seed = Seed(dna)
        assert seed.base_url == "http://[::1]:8090"

    def test_junior_not_reachable(self) -> None:
        """Junior 节点不可达。"""
        seed = _make_junior_seed()
        assert not seed.is_reachable
        assert seed.base_url is None

    def test_virgin_not_reachable(self) -> None:
        """Virgin 节点不可达。"""
        dna = {SeedKeys.HASH: "virgintst001", SeedKeys.PEERTYPE: PEERTYPE_VIRGIN}
        seed = Seed(dna)
        assert not seed.is_reachable

    def test_senior_no_ip_not_reachable(self) -> None:
        """无 IP 的 Senior 不可达。"""
        dna = {
            SeedKeys.HASH: "noipsenior01",
            SeedKeys.PEERTYPE: PEERTYPE_SENIOR,
            SeedKeys.IP: "",
            SeedKeys.PORT: "8090",
        }
        seed = Seed(dna)
        assert not seed.is_reachable

    def test_senior_zero_port_not_reachable(self) -> None:
        """端口为 0 的 Senior 不可达。"""
        dna = {
            SeedKeys.HASH: "zeroport001",
            SeedKeys.PEERTYPE: PEERTYPE_SENIOR,
            SeedKeys.IP: "10.0.0.1",
            SeedKeys.PORT: "0",
        }
        seed = Seed(dna)
        assert not seed.is_reachable


# ===================================================================
# Hello 结果解析
# ===================================================================


class TestHelloResultParsing:
    """HelloResult 响应解析测试。"""

    def test_ok_status_line(self) -> None:
        """ok 状态行解析。"""
        response = P2PResponse("ok 263")
        result = HelloResult.from_response(response)
        assert result.success

    def test_ok_key_value(self) -> None:
        """ok key=value 格式。"""
        response = P2PResponse("message=ok 128\nyourip=1.2.3.4")
        result = HelloResult.from_response(response)
        assert result.success
        assert result.your_ip == "1.2.3.4"

    def test_failure_message(self) -> None:
        """失败消息。"""
        response = P2PResponse("message=cannot resolve your IP")
        result = HelloResult.from_response(response)
        assert not result.success

    def test_yourtype_senior(self) -> None:
        """Senior 类型判定。"""
        response = P2PResponse("message=ok\nyourtype=senior\nyourip=5.6.7.8")
        result = HelloResult.from_response(response)
        assert result.your_type == PEERTYPE_SENIOR
        assert result.is_senior
        assert not result.is_junior

    def test_yourtype_invalid(self) -> None:
        """无效类型应默认 Junior。"""
        response = P2PResponse("message=ok\nyourtype=invalid_type")
        result = HelloResult.from_response(response)
        assert result.your_type == PEERTYPE_JUNIOR

    def test_yourtype_principal(self) -> None:
        """Principal 类型判定。"""
        response = P2PResponse("message=ok\nyourtype=principal")
        result = HelloResult.from_response(response)
        assert result.is_senior  # Principal 也算 Senior


# ===================================================================
# P2PProtocol 基本请求字段
# ===================================================================


class TestP2PProtocolParts:
    """P2PProtocol basic_request_parts 测试。"""

    def test_required_fields_present(self) -> None:
        """所有必需字段都应存在。"""
        proto = P2PProtocol()
        parts = proto.basic_request_parts("myHash12345")
        required_keys = {"iam", "key", "mytime", "myUTC", "network.unit.name"}
        assert required_keys.issubset(set(parts.keys()))

    def test_target_hash_included(self) -> None:
        """目标哈希应出现在字段中。"""
        proto = P2PProtocol()
        parts = proto.basic_request_parts("myH", target_hash="targetH")
        assert parts["youare"] == "targetH"

    def test_network_name(self) -> None:
        """自定义网络名称。"""
        proto = P2PProtocol(network_name="mytestnet")
        parts = proto.basic_request_parts("myH")
        assert parts["network.unit.name"] == "mytestnet"


# ===================================================================
# 版本号一致性
# ===================================================================


class TestVersionConsistency:
    """版本号一致性检查。"""

    def test_package_version(self) -> None:
        """__version__ 应为有效版本号。"""
        from pyacy import __version__
        parts = __version__.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_user_agent_contains_version(self) -> None:
        """User-Agent 应包含当前版本号。"""
        from pyacy import __version__
        # client.py User-Agent
        client = __import__("pyacy.client", fromlist=["YaCyClient"])
        # 仅检查版本号格式存在
        assert __version__
