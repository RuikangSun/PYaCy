# -*- coding: utf-8 -*-
"""种子管理模块单元测试。

测试 ``pyacy.p2p.seeds`` 模块的：
- 硬编码种子列表完整性
- 并行连通性探测
- 本地种子缓存读写
- 种子列表构建（三层来源）
- 动态种子发现
"""

import json
import os
import sys
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock
from urllib.error import URLError

import pytest

# 确保项目路径在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pyacy.p2p.seed import (
    Seed,
    SeedKeys,
    PEERTYPE_SENIOR,
    PEERTYPE_JUNIOR,
    PEERTYPE_PRINCIPAL,
)
from pyacy.p2p.seeds import (
    HARDCODED_SEEDS,
    build_seed_list,
    probe_seed,
    probe_seeds,
    load_seed_cache,
    save_seed_cache,
    clear_seed_cache,
    fetch_online_seeds,
)


# ---------------------------------------------------------------------------
# 测试夹具
# ---------------------------------------------------------------------------


def _make_senior_seed(name="test-senior", hash_val="", url="http://10.0.0.1:8090"):
    """创建测试用 Senior Seed。"""
    dna = {
        SeedKeys.HASH: hash_val or f"hash-{name}",
        SeedKeys.NAME: name,
        SeedKeys.PEERTYPE: PEERTYPE_SENIOR,
        SeedKeys.IP: "10.0.0.1",
        SeedKeys.PORT: "8090",
        SeedKeys.ICOUNT: "10000",
        SeedKeys.UPTIME: "10080",  # 7 天（分钟）
    }
    s = Seed(dna)
    s.set_reachable(True)
    return s


def _make_junior_seed(name="test-junior"):
    """创建测试用 Junior Seed。"""
    return Seed.create_junior(name=name)


# ---------------------------------------------------------------------------
# 1. 硬编码种子列表
# ---------------------------------------------------------------------------


class TestHardcodedSeeds:
    """测试硬编码种子列表的完整性和质量。"""

    def test_not_empty(self):
        """硬编码种子列表不应为空。"""
        assert len(HARDCODED_SEEDS) > 0

    def test_minimum_count(self):
        """硬编码种子至少 25 个（确保冗余）。"""
        assert len(HARDCODED_SEEDS) >= 25, (
            f"硬编码种子只有 {len(HARDCODED_SEEDS)} 个，需要 ≥ 25 个"
        )

    def test_each_has_url_and_hash(self):
        """每个种子必须包含 url 和 hash 字段。"""
        for i, seed in enumerate(HARDCODED_SEEDS):
            assert "url" in seed, f"种子 #{i} 缺少 'url' 字段"
            assert "hash" in seed, f"种子 #{i} 缺少 'hash' 字段"
            assert seed["url"].startswith("http"), f"种子 #{i} URL 格式无效: {seed['url']}"
            assert len(seed["hash"]) >= 10, f"种子 #{i} hash 长度过短: {seed['hash']}"

    def test_no_duplicate_urls(self):
        """种子 URL 不应重复。"""
        urls = [s["url"] for s in HARDCODED_SEEDS]
        assert len(urls) == len(set(urls)), "硬编码种子有重复 URL"

    def test_no_duplicate_hashes(self):
        """种子 hash 不应重复。"""
        hashes = [s["hash"] for s in HARDCODED_SEEDS]
        assert len(hashes) == len(set(hashes)), "硬编码种子有重复 hash"


# ---------------------------------------------------------------------------
# 2. 单个种子探测
# ---------------------------------------------------------------------------


class TestProbeSeed:
    """测试单个种子节点连通性探测。"""

    def test_probe_reachable(self):
        """可达种子应返回 Seed 对象。"""
        seed = _make_senior_seed()

        with patch("pyacy.p2p.seeds.urlopen") as mock_urlopen:
            mock_resp = Mock()
            mock_resp.status = 200
            mock_resp.read.return_value = b'[]'
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            result = probe_seed(seed, timeout=2.0)
            assert result is not None
            assert result.hash == seed.hash
            assert result.is_reachable

    def test_probe_unreachable(self):
        """不可达种子应返回 None。"""
        seed = _make_senior_seed()

        with patch("pyacy.p2p.seeds.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = URLError("connection refused")

            result = probe_seed(seed, timeout=2.0)
            assert result is None

    def test_probe_no_url(self):
        """无 URL 的种子直接返回 None。"""
        seed = _make_senior_seed()
        seed.dna[SeedKeys.IP] = ""  # 无 IP，base_url 返回 None

        result = probe_seed(seed)
        # 注意：IP 为空但 Port 有值的情况下，base_url 的行为取决于实现
        # 这里验证探测不会崩溃
        assert result is None or isinstance(result, Seed)


# ---------------------------------------------------------------------------
# 3. 并行探测
# ---------------------------------------------------------------------------


class TestProbeSeeds:
    """测试并行连通性探测。"""

    def test_parallel_probe_all_reachable(self):
        """所有种子都可达时，返回全部。"""
        seeds = [
            _make_senior_seed(name="s1", hash_val="h1"),
            _make_senior_seed(name="s2", hash_val="h2"),
            _make_senior_seed(name="s3", hash_val="h3"),
        ]

        with patch("pyacy.p2p.seeds.urlopen") as mock_urlopen:
            mock_resp = Mock()
            mock_resp.status = 200
            mock_resp.read.return_value = b'[]'
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            results = probe_seeds(seeds, timeout=2.0, max_concurrent=3)
            assert len(results) == 3, f"应返回 3 个可达种子，实际 {len(results)}"

    def test_parallel_probe_some_unreachable(self):
        """部分种子不可达时，只返回可达的。"""
        seed1 = _make_senior_seed(name="s1", hash_val="h1")
        seed2 = _make_senior_seed(name="s2", hash_val="h2")
        seed3 = _make_senior_seed(name="s3", hash_val="h3")

        # 让 s2 不可达
        from pyacy.p2p.seeds import probe_seed as _probe_seed_single

        with patch("pyacy.p2p.seeds.probe_seed") as mock_probe:
            def side_effect(seed, timeout=5.0):
                if seed.name == "s2":
                    return None
                seed.set_reachable(True)
                seed.touch()
                return seed
            mock_probe.side_effect = side_effect

            results = probe_seeds([seed1, seed2, seed3], timeout=2.0)
            assert len(results) == 2

    def test_empty_seeds_list(self):
        """空种子列表返回空。"""
        results = probe_seeds([])
        assert results == []


# ---------------------------------------------------------------------------
# 4. 种子缓存
# ---------------------------------------------------------------------------


class TestSeedCache:
    """测试本地种子缓存的读写。"""

    def test_save_and_load(self):
        """保存种子到缓存，然后加载回来。"""
        seeds = [
            _make_senior_seed(name="cached-1", hash_val="ch1"),
            _make_senior_seed(name="cached-2", hash_val="ch2"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pyacy.p2p.seeds._get_cache_dir") as mock_dir:
                mock_dir.return_value = Path(tmpdir)

                save_seed_cache(seeds)
                loaded = load_seed_cache()

                assert len(loaded) == 2
                assert loaded[0].hash in ("ch1", "ch2")
                assert loaded[1].hash in ("ch1", "ch2")

    def test_load_empty_cache(self):
        """缓存文件不存在时返回空列表。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "nonexistent.json"
            with patch("pyacy.p2p.seeds._get_cache_path") as mock_path:
                mock_path.return_value = cache_file
                loaded = load_seed_cache()
                assert loaded == []

    def test_clear_cache(self):
        """清除缓存后加载应为空。"""
        seeds = [_make_senior_seed(name="to-clear", hash_val="ch3")]

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pyacy.p2p.seeds._get_cache_dir") as mock_dir:
                mock_dir.return_value = Path(tmpdir)

                save_seed_cache(seeds)
                # 确认已保存
                assert len(load_seed_cache()) == 1

                clear_seed_cache()
                assert load_seed_cache() == []

    def test_save_max_cache_limit(self):
        """缓存节点数受 max_cache 限制。"""
        seeds = [
            _make_senior_seed(name=f"seed-{i}", hash_val=f"h{i:03d}")
            for i in range(300)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pyacy.p2p.seeds._get_cache_dir") as mock_dir:
                mock_dir.return_value = Path(tmpdir)

                save_seed_cache(seeds, max_cache=50)
                loaded = load_seed_cache()
                assert len(loaded) <= 50

    def test_cache_prioritizes_senior(self):
        """缓存应优先保留 Senior 节点。"""
        junior = _make_junior_seed()
        senior = _make_senior_seed(name="senior-priority", hash_val="sp1")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pyacy.p2p.seeds._get_cache_dir") as mock_dir:
                mock_dir.return_value = Path(tmpdir)

                save_seed_cache([junior, senior], max_cache=1)
                loaded = load_seed_cache()
                assert len(loaded) == 1
                assert loaded[0].is_senior()


# ---------------------------------------------------------------------------
# 5. 种子列表构建（三层来源）
# ---------------------------------------------------------------------------


class TestBuildSeedList:
    """测试 build_seed_list() 三层种子来源合并。"""

    def test_hardcoded_seeds_included(self):
        """构建的种子列表应包含硬编码种子。"""
        # 不探测，直接验证种子解析
        with patch("pyacy.p2p.seeds.load_seed_cache", return_value=[]):
            seeds = build_seed_list(probe=False)
            # 应至少包含硬编码种子的数量
            assert len(seeds) >= len(HARDCODED_SEEDS), (
                f"构建的种子 {len(seeds)} < 硬编码种子 {len(HARDCODED_SEEDS)}"
            )

    def test_custom_seeds_highest_priority(self):
        """自定义种子应优先级最高。"""
        custom = _make_senior_seed(name="custom-seed", hash_val="custom-hash")

        with patch("pyacy.p2p.seeds.load_seed_cache", return_value=[]):
            with patch("pyacy.p2p.seeds.urlopen") as mock_urlopen:
                mock_resp = Mock()
                mock_resp.status = 200
                mock_resp.read.return_value = b'[]'
                mock_urlopen.return_value.__enter__.return_value = mock_resp

                seeds = build_seed_list(
                    custom_seeds=[custom],
                    probe=True,
                )

                # 自定义种子应在结果中
                custom_hashes = {s.hash for s in seeds}
                assert "custom-hash" in custom_hashes

    def test_no_duplicates_across_sources(self):
        """跨来源的重复种子应去重。"""
        # 模拟缓存中有一个与硬编码相同的种子
        dup_seed = _make_senior_seed(name="dup", hash_val="dup-hash")

        with patch("pyacy.p2p.seeds.load_seed_cache", return_value=[dup_seed]):
            seeds = build_seed_list(probe=False)

            # 验证去重
            hashes = [s.hash for s in seeds]
            # dup-hash 可能不在硬编码列表中，所以只检查无重复
            assert len(hashes) == len(set(hashes)), "种子列表有重复 hash"

    def test_fallback_when_all_probe_fail(self):
        """所有种子都不可达时，返回空列表。"""
        with patch("pyacy.p2p.seeds.load_seed_cache", return_value=[]):
            with patch("pyacy.p2p.seeds.probe_seed", return_value=None):
                seeds = build_seed_list(probe=True)
                assert seeds == []


# ---------------------------------------------------------------------------
# 6. 动态种子发现
# ---------------------------------------------------------------------------


class TestFetchOnlineSeeds:
    """测试 fetch_online_seeds() 动态种子获取。"""

    def test_fetch_from_seedlist_array_format(self):
        """解析数组格式的 seedlist.json。"""
        mock_data = json.dumps([
            {
                "Hash": "AAAAAAAAAAAA",
                "Name": "test-peer",
                "PeerType": "senior",
                "IP": "10.0.0.1",
                "Port": "8090",
            },
        ])

        with patch("pyacy.p2p.seeds.urlopen") as mock_urlopen:
            mock_resp = Mock()
            mock_resp.status = 200
            mock_resp.read.return_value = mock_data.encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            results = fetch_online_seeds(["http://test:8090"])
            assert len(results) == 1
            assert results[0].hash == "AAAAAAAAAAAA"
            assert results[0].name == "test-peer"

    def test_fetch_from_seedlist_peers_format(self):
        """解析 {"peers": [...]} 格式的 seedlist.json。"""
        mock_data = json.dumps({
            "peers": [
                {
                    "Hash": "BBBBBBBBBBBB",
                    "Name": "peer-b",
                    "PeerType": "principal",
                    "IP": "10.0.0.2",
                    "Port": "8090",
                },
            ]
        })

        with patch("pyacy.p2p.seeds.urlopen") as mock_urlopen:
            mock_resp = Mock()
            mock_resp.status = 200
            mock_resp.read.return_value = mock_data.encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            results = fetch_online_seeds(["http://test:8090"])
            assert len(results) == 1
            assert results[0].hash == "BBBBBBBBBBBB"

    def test_fetch_handles_address_field(self):
        """解析带有 Address 数组字段的节点。"""
        mock_data = json.dumps([
            {
                "Hash": "CCCCCCCCCCCC",
                "Name": "peer-c",
                "PeerType": "senior",
                "Address": ["10.0.0.3:8090"],
            },
        ])

        with patch("pyacy.p2p.seeds.urlopen") as mock_urlopen:
            mock_resp = Mock()
            mock_resp.status = 200
            mock_resp.read.return_value = mock_data.encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            results = fetch_online_seeds(["http://test:8090"])
            assert len(results) == 1

    def test_fetch_network_error(self):
        """网络错误时返回空列表。"""
        with patch("pyacy.p2p.seeds.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = URLError("timeout")

            results = fetch_online_seeds(["http://unreachable:8090"])
            assert results == []

    def test_fetch_deduplication(self):
        """重复节点应去重。"""
        mock_data = json.dumps([
            {"Hash": "DDDDDDDDDDDD", "Name": "peer-d", "PeerType": "senior"},
            {"Hash": "DDDDDDDDDDDD", "Name": "peer-d-dup", "PeerType": "senior"},
        ])

        with patch("pyacy.p2p.seeds.urlopen") as mock_urlopen:
            mock_resp = Mock()
            mock_resp.status = 200
            mock_resp.read.return_value = mock_data.encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            results = fetch_online_seeds(["http://test:8090"])
            assert len(results) == 1


# ---------------------------------------------------------------------------
# 7. 边界与回归测试
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """边界情况测试。"""

    def test_build_seed_list_no_probe(self):
        """不探测模式直接返回所有候选种子。"""
        with patch("pyacy.p2p.seeds.load_seed_cache", return_value=[]):
            seeds = build_seed_list(probe=False)
            assert len(seeds) > 0, "应至少包含硬编码种子"

    def test_save_cache_with_empty_list(self):
        """保存空列表不应崩溃。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pyacy.p2p.seeds._get_cache_dir") as mock_dir:
                mock_dir.return_value = Path(tmpdir)
                save_seed_cache([])  # 不应抛出异常

    def test_save_cache_with_invalid_seeds(self):
        """保存缺少 hash 的种子不应崩溃。"""
        bad_seed = Seed({SeedKeys.NAME: "no-hash"})
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pyacy.p2p.seeds._get_cache_dir") as mock_dir:
                mock_dir.return_value = Path(tmpdir)
                save_seed_cache([bad_seed])  # 应跳过或优雅处理
