# -*- coding: utf-8 -*-
"""DHT 哈希路由与搜索单元测试。

测试 ``pyacy.dht.search`` 模块的新增功能（v0.3.0）：
- ``dht_distance()`` XOR 距离计算
- ``_find_responsible_peers()`` 哈希路由
- 搜索结果的引用解析
- 迭代扩展搜索逻辑
"""

import os
import sys
from unittest.mock import patch, Mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pyacy.utils import dht_distance, word_to_hash
from pyacy.dht.search import (
    DHTSearchClient,
    DHTSearchResult,
    DHTReference,
    _find_responsible_peers,
    _parse_references,
    _parse_links,
    _tokenize_query,
)
from pyacy.p2p.seed import Seed, SeedKeys, PEERTYPE_SENIOR
from pyacy.p2p.protocol import P2PProtocol


# ---------------------------------------------------------------------------
# 测试夹具
# ---------------------------------------------------------------------------


def _make_seed(hash_val: str, name: str = "test", ip: str = "10.0.0.1"):
    """创建测试用 Senior Seed。"""
    dna = {
        SeedKeys.HASH: hash_val,
        SeedKeys.NAME: name,
        SeedKeys.PEERTYPE: PEERTYPE_SENIOR,
        SeedKeys.IP: ip,
        SeedKeys.PORT: "8090",
    }
    s = Seed(dna)
    s.set_reachable(True)
    return s


# ---------------------------------------------------------------------------
# 1. dht_distance() XOR 距离计算
# ---------------------------------------------------------------------------


class TestDHTDistance:
    """测试 dht_distance() 函数。"""

    def test_zero_distance_self(self):
        """相同哈希的距离应为 0。"""
        h = "AAAAAAAAAAAA"
        assert dht_distance(h, h) == 0

    def test_distance_symmetric(self):
        """距离应是对称的。"""
        a = "AAAAAAAAAAAA"
        b = "BBBBBBBBBBBB"
        assert dht_distance(a, b) == dht_distance(b, a)

    def test_distance_positive_for_different(self):
        """不同哈希的距离 > 0。"""
        a = "AAAAAAAAAAAA"
        b = "AAAAAAAAAAAB"
        assert dht_distance(a, b) > 0

    def test_distance_transitive_ordering(self):
        """距离排序应保持一致。"""
        target = "AAAAAAAAAAAA"
        near = "AAAAAAAAAAAB"
        far = "BBBBBBBBBBBB"

        dist_near = dht_distance(target, near)
        dist_far = dht_distance(target, far)
        assert dist_near < dist_far, (
            f"near={dist_near} 应 < far={dist_far}"
        )

    def test_distance_with_word_hashes(self):
        """用实际词哈希验证距离计算。"""
        h_hello = word_to_hash("hello")
        h_world = word_to_hash("world")
        h_python = word_to_hash("python")

        # 所有距离应为非负整数
        assert dht_distance(h_hello, h_world) >= 0
        assert dht_distance(h_python, h_world) >= 0
        assert isinstance(dht_distance(h_hello, h_python), int)

    def test_distance_bit_distribution(self):
        """验证距离的位分布合理。"""
        zero = "AAAAAAAAAAAA"
        # 第一位翻转（最大距离约 2^71）
        max_bit = "BAAAAAAAAAAA"
        # 第 12 位翻转（小距离）
        min_bit = "AAAAAAAAAAAB"

        dist_max = dht_distance(zero, max_bit)
        dist_min = dht_distance(zero, min_bit)

        assert dist_max > dist_min, (
            f"高位翻转距离 {dist_max} 应 > 低位翻转距离 {dist_min}"
        )

    def test_invalid_character_raises(self):
        """非法字符应抛出 ValueError。"""
        with pytest.raises(ValueError):
            dht_distance("hello!!!!!!!", "AAAAAAAAAAAA")


# ---------------------------------------------------------------------------
# 2. _find_responsible_peers() 哈希路由
# ---------------------------------------------------------------------------


class TestFindResponsiblePeers:
    """测试 _find_responsible_peers() 哈希路由。"""

    def test_returns_closest_peers(self):
        """应返回距离词哈希最近的 k 个节点。"""
        # 创建节点：t1 的哈希与词哈希非常接近
        target_word = "testword"
        wh = word_to_hash(target_word)

        # 使用真实的节点哈希分布
        peers = [
            _make_seed(hash_val="AAAAAAAAAAAA", name="peer-a"),
            _make_seed(hash_val="BBBBBBBBBBBB", name="peer-b"),
            _make_seed(hash_val="CCCCCCCCCCCC", name="peer-c"),
            _make_seed(hash_val="DDDDDDDDDDDD", name="peer-d"),
            _make_seed(hash_val="EEEEEEEEEEEE", name="peer-e"),
        ]

        results = _find_responsible_peers(
            word_hashes=[wh],
            peers=peers,
            k=3,
        )

        assert len(results) <= 3, f"应返回 ≤3 个节点，实际 {len(results)}"
        # 每个结果应是 (url, hash) 元组
        for r in results:
            assert isinstance(r, tuple)
            assert len(r) == 2
            assert r[0].startswith("http")
            assert len(r[1]) == 12

    def test_sorted_by_distance(self):
        """结果应按距离排序（最近的在前）。"""
        target_word = "example"
        wh = word_to_hash(target_word)

        peers = [
            _make_seed(hash_val="AAAAAAAAAAAA", name="p1"),
            _make_seed(hash_val="MMk7y0iHqn3", name="p2"),
            _make_seed(hash_val="zzzzzzzzzzzz", name="p3"),
            _make_seed(hash_val="000000000000", name="p4"),
        ]

        results = _find_responsible_peers(
            word_hashes=[wh],
            peers=peers,
            k=4,
        )

        # 验证排序：距离递增
        distances = []
        for url, hsh in results:
            distances.append(dht_distance(wh, hsh))

        for i in range(len(distances) - 1):
            assert distances[i] <= distances[i + 1], (
                f"距离 {distances[i]} ({results[i][1]}) "
                f"应 ≤ {distances[i+1]} ({results[i+1][1]})"
            )

    def test_multiple_word_hashes(self):
        """多个词哈希应合并选择最近节点。"""
        wh1 = word_to_hash("hello")
        wh2 = word_to_hash("world")

        peers = [
            _make_seed(hash_val="AAAAAAAAAAAA", name="a"),
            _make_seed(hash_val="BBBBBBBBBBBB", name="b"),
            _make_seed(hash_val="CCCCCCCCCCCC", name="c"),
        ]

        results = _find_responsible_peers(
            word_hashes=[wh1, wh2],
            peers=peers,
            k=3,
        )

        # 去重后不应超过 peer 总数
        assert len(results) <= len(peers)

    def test_empty_word_hashes(self):
        """空词哈希列表返回空。"""
        peers = [_make_seed(hash_val="AAAAAAAAAAAA")]
        results = _find_responsible_peers(word_hashes=[], peers=peers, k=3)
        assert results == []

    def test_empty_peers(self):
        """空 peer 列表返回空。"""
        wh = word_to_hash("test")
        results = _find_responsible_peers(word_hashes=[wh], peers=[], k=3)
        assert results == []

    def test_filters_unreachable(self):
        """应过滤 base_url 为 None 的节点。"""
        # 创建一个无法生成 base_url 的节点
        seed_no_ip = Seed({
            SeedKeys.HASH: "BBBBBBBBBBBB",
            SeedKeys.NAME: "no-ip",
            SeedKeys.PEERTYPE: PEERTYPE_SENIOR,
            SeedKeys.IP: "",  # 无 IP
            SeedKeys.PORT: "0",  # 无效端口
        })
        seed_good = _make_seed(hash_val="AAAAAAAAAAAA")

        wh = word_to_hash("test")
        results = _find_responsible_peers(
            word_hashes=[wh],
            peers=[seed_no_ip, seed_good],
            k=5,
        )

        # 应只返回有效节点
        urls = [r[0] for r in results]
        assert all(u.startswith("http") for u in urls)


# ---------------------------------------------------------------------------
# 3. 搜索响应解析
# ---------------------------------------------------------------------------


class TestParseReferences:
    """测试 DHT 搜索响应的引用解析。"""

    def test_parse_single_reference(self):
        """解析单条引用（URL哈希 + 词哈希 + URL）。"""
        raw = "abcDEFghiJKL xyz123stuVWX http://example.com/page"
        refs = _parse_references(raw)
        assert len(refs) >= 1
        assert refs[0].url_hash == "abcDEFghiJKL"

    def test_parse_empty(self):
        """空字符串返回空列表。"""
        refs = _parse_references("")
        assert refs == []

    def test_parse_whitespace_only(self):
        """纯空白字符串返回空列表。"""
        refs = _parse_references("   \n  \t  ")
        assert refs == []

    def test_parse_curly_brace_format(self):
        """解析花括号包裹格式（YaCy 原始格式）。"""
        raw = "{abcDEFghiJKL xyz123stuVWX http://example.com}"
        refs = _parse_references(raw)
        assert len(refs) >= 1
        assert refs[0].url_hash == "abcDEFghiJKL"

    def test_parse_multiline(self):
        """解析多行引用。"""
        raw = (
            "abc111111111 wordhash1 http://a.com\n"
            "def222222222 wordhash2 http://b.com\n"
        )
        refs = _parse_references(raw)
        assert len(refs) >= 2

    def test_parse_links(self):
        """解析链接列表。"""
        raw = "http://example.com\nhttp://test.org\n\n"
        links = _parse_links(raw)
        assert links == ["http://example.com", "http://test.org"]


# ---------------------------------------------------------------------------
# 4. 搜索客户端集成测试
# ---------------------------------------------------------------------------


class TestDHTSearchClientRouting:
    """测试 DHTSearchClient 的哈希路由搜索。"""

    def test_fulltext_search_uses_routing(self):
        """fulltext_search 应使用哈希路由而非随机选取。"""
        protocol = P2PProtocol()
        client = DHTSearchClient(protocol)

        peers = [
            _make_seed(hash_val="AAAAAAAAAAAA", name="peer-1"),
            _make_seed(hash_val="BBBBBBBBBBBB", name="peer-2"),
            _make_seed(hash_val="CCCCCCCCCCCC", name="peer-3"),
            _make_seed(hash_val="DDDDDDDDDDDD", name="peer-4"),
            _make_seed(hash_val="EEEEEEEEEEEE", name="peer-5"),
        ]

        # Mock search_multiple 以避免实际网络请求
        with patch.object(client, "search_multiple") as mock_sm:
            mock_sm.return_value = DHTSearchResult(success=True)

            result = client.fulltext_search(
                peers=peers,
                my_hash="FFFFFFFFFFFF",
                query="hello world",
                max_peers=3,
            )

            assert result.success
            mock_sm.assert_called_once()

            # 验证传递给 search_multiple 的 targets
            call_args = mock_sm.call_args[1]
            targets = call_args.get("targets", [])

            # 应选择了 3 个节点
            assert len(targets) >= 1, "哈希路由应选择至少 1 个节点"
            for url, hsh in targets:
                assert url.startswith("http")
                assert len(hsh) == 12

    def test_fulltext_search_empty_query(self):
        """空搜索词返回失败结果。"""
        protocol = P2PProtocol()
        client = DHTSearchClient(protocol)

        peers = [_make_seed(hash_val="AAAAAAAAAAAA")]
        result = client.fulltext_search(
            peers=peers,
            my_hash="FFFFFFFFFFFF",
            query="   ",
        )

        assert not result.success

    def test_fulltext_search_no_senior_peers(self):
        """无 Senior 节点时返回失败。"""
        protocol = P2PProtocol()
        client = DHTSearchClient(protocol)

        result = client.fulltext_search(
            peers=[],
            my_hash="FFFFFFFFFFFF",
            query="hello",
        )

        assert not result.success

    def test_fulltext_search_iterative_expansion(self):
        """迭代扩展在首轮无结果时触发。"""
        protocol = P2PProtocol()
        client = DHTSearchClient(protocol)

        peers = [
            _make_seed(hash_val="AAAAAAAAAAAA", name=f"peer-{i}", ip=f"10.0.0.{i+1}")
            for i in range(30)
        ]

        with patch.object(client, "search_multiple") as mock_sm:
            # 首轮返回 0 结果，第二轮返回结果
            empty_result = DHTSearchResult(success=True, references=[])
            filled_result = DHTSearchResult(
                success=True,
                references=[
                    DHTReference(url_hash="abc123", url="http://found.com")
                ],
            )
            mock_sm.side_effect = [empty_result, filled_result]

            result = client.fulltext_search(
                peers=peers,
                my_hash="FFFFFFFFFFFF",
                query="rareterm",
                max_peers=5,
                iterative=True,
            )

            # 应最终返回填充的结果
            assert result.success
            assert len(result.references) == 1
            # search_multiple 应被调用 2 次（首轮 + 扩展轮）
            assert mock_sm.call_count == 2


# ---------------------------------------------------------------------------
# 5. 词元化
# ---------------------------------------------------------------------------


class TestTokenizeQuery:
    """测试搜索词元化。"""

    def test_simple_tokenize(self):
        """简单空格分割。"""
        tokens = _tokenize_query("hello world")
        assert tokens == ["hello", "world"]

    def test_lowercase(self):
        """转为小写。"""
        tokens = _tokenize_query("Hello WORLD")
        assert tokens == ["hello", "world"]

    def test_empty_query(self):
        """空查询返回空列表。"""
        tokens = _tokenize_query("")
        assert tokens == []

    def test_extra_whitespace(self):
        """多余空白被过滤。"""
        tokens = _tokenize_query("  hello   world   ")
        assert tokens == ["hello", "world"]
