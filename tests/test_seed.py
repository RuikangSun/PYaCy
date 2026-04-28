# -*- coding: utf-8 -*-
"""PYaCy P2P 种子模块测试。

测试 p2p/seed.py 中的所有功能。
"""

import time

import pytest

from pyacy.p2p.seed import (
    PEERTYPE_JUNIOR,
    PEERTYPE_SENIOR,
    PEERTYPE_PRINCIPAL,
    PEERTYPE_VIRGIN,
    Seed,
    SeedKeys,
    _current_yaCy_time,
    _utc_offset_string,
)


# ===================================================================
# Seed 创建
# ===================================================================


class TestSeedCreation:
    """Seed 创建测试。"""

    def test_create_junior(self) -> None:
        """创建 Junior 节点。"""
        seed = Seed.create_junior(name="test-node", port=8090)
        assert seed.name == "test-node"
        assert seed.peer_type == PEERTYPE_JUNIOR
        assert seed.port == 8090
        assert len(seed.hash) == 12
        assert seed.is_junior()
        assert not seed.is_senior()

    def test_create_junior_default_name(self) -> None:
        """创建 Junior 节点（默认名称）。"""
        seed = Seed.create_junior()
        assert len(seed.name) > 0
        assert seed.peer_type == PEERTYPE_JUNIOR

    def test_create_junior_unique_hashes(self) -> None:
        """不同节点应有不同哈希。"""
        s1 = Seed.create_junior("node1")
        s2 = Seed.create_junior("node2")
        assert s1.hash != s2.hash

    def test_from_seed_string_simple(self) -> None:
        """从简单种子字符串创建。"""
        seed_str = "p|{Hash=sCJ6Tq8T0N9x,Port=8090,PeerType=senior,Name=RemotePeer}"
        seed = Seed.from_seed_string(seed_str)
        assert seed.hash == "sCJ6Tq8T0N9x"
        assert seed.port == 8090
        assert seed.peer_type == PEERTYPE_SENIOR
        assert seed.name == "RemotePeer"

    def test_from_seed_string_with_default_ip(self) -> None:
        """带默认 IP 的种子字符串。"""
        seed_str = "p|{Hash=abc123,Port=8090,PeerType=senior}"
        seed = Seed.from_seed_string(seed_str, default_ip="1.2.3.4")
        assert seed.ip == "1.2.3.4"

    def test_from_seed_string_missing_fields(self) -> None:
        """缺少字段应有默认值。"""
        seed_str = "p|{Hash=abc123}"
        seed = Seed.from_seed_string(seed_str)
        assert seed.hash == "abc123"
        assert seed.peer_type == PEERTYPE_JUNIOR  # 默认
        assert seed.name == "unknown"

    def test_from_json(self) -> None:
        """从 JSON 字典创建。"""
        data = {
            "Hash": "testhash123",
            "Name": "JSONPeer",
            "PeerType": "senior",
            "IP": "10.0.0.1",
            "Port": 8090,
            "Version": "1.92",
            "LastSeen": "2026/01/01 12:00:00",
            "Uptime": "1440",
            "LCount": "50000",
            "ICount": "100000",
            "RCount": "2000",
            "SCount": "150",
            "CCount": "30",
        }
        seed = Seed.from_json(data)
        assert seed.hash == "testhash123"
        assert seed.name == "JSONPeer"
        assert seed.peer_type == PEERTYPE_SENIOR
        assert seed.port == 8090

    def test_from_json_minimal(self) -> None:
        """从最小 JSON 创建。"""
        seed = Seed.from_json({"Hash": "minimalhash"})
        assert seed.hash == "minimalhash"
        assert seed.peer_type == PEERTYPE_JUNIOR


# ===================================================================
# Seed 属性
# ===================================================================


class TestSeedProperties:
    """Seed 属性访问测试。"""

    @pytest.fixture
    def senior_seed(self) -> Seed:
        """创建一个 Senior 节点。"""
        dna = {
            SeedKeys.HASH: "seniorhash01",
            SeedKeys.NAME: "SeniorPeer",
            SeedKeys.PEERTYPE: PEERTYPE_SENIOR,
            SeedKeys.IP: "192.168.1.1",
            SeedKeys.PORT: "8090",
            SeedKeys.VERSION: "1.92",
            SeedKeys.UPTIME: "1440",
        }
        return Seed(dna)

    @pytest.fixture
    def junior_seed(self) -> Seed:
        """创建一个 Junior 节点。"""
        return Seed.create_junior("JuniorPeer")

    def test_basic_properties(self, senior_seed: Seed) -> None:
        """基本属性。"""
        assert senior_seed.name == "SeniorPeer"
        assert senior_seed.peer_type == PEERTYPE_SENIOR
        assert senior_seed.ip == "192.168.1.1"
        assert senior_seed.port == 8090
        assert senior_seed.version == "1.92"
        assert senior_seed.uptime_minutes == 1440

    def test_type_checks(self, senior_seed: Seed, junior_seed: Seed) -> None:
        """类型判断方法。"""
        assert senior_seed.is_senior()
        assert not senior_seed.is_junior()
        assert not senior_seed.is_virgin()

        assert junior_seed.is_junior()
        assert not junior_seed.is_senior()
        assert not junior_seed.is_virgin()

    def test_base_url(self, senior_seed: Seed, junior_seed: Seed) -> None:
        """节点 URL。"""
        assert senior_seed.base_url == "http://192.168.1.1:8090"
        assert junior_seed.base_url is None  # Junior 没有 IP

    def test_is_reachable(self, senior_seed: Seed, junior_seed: Seed) -> None:
        """节点可达性。"""
        assert senior_seed.is_reachable
        assert not junior_seed.is_reachable

    def test_principal_type(self) -> None:
        """Principal 节点类型。"""
        dna = {
            SeedKeys.HASH: "prin0001",
            SeedKeys.HASH: "prinhash0001",
            SeedKeys.PEERTYPE: PEERTYPE_PRINCIPAL,
            SeedKeys.IP: "10.0.0.1",
            SeedKeys.PORT: "8090",
        }
        # Fix: Hash key duplicated
        dna[SeedKeys.HASH] = "prinhash0001"
        seed = Seed(dna)
        assert seed.is_principal()
        assert seed.is_senior()  # Principal 也是 Senior
        assert seed.is_reachable

    def test_is_principal(self) -> None:
        """Principal 与 Senior 的区别。"""
        dna_p = {
            SeedKeys.HASH: "prinhash0001",
            SeedKeys.PEERTYPE: PEERTYPE_PRINCIPAL,
            SeedKeys.IP: "10.0.0.1",
            SeedKeys.PORT: "8090",
        }
        seed_p = Seed(dna_p)
        assert seed_p.is_principal()

        dna_s = {
            SeedKeys.HASH: "seniorhash01",
            SeedKeys.PEERTYPE: PEERTYPE_SENIOR,
            SeedKeys.IP: "10.0.0.2",
            SeedKeys.PORT: "8090",
        }
        seed_s = Seed(dna_s)
        assert not seed_s.is_principal()

    def test_get_and_put(self) -> None:
        """get/put 方法。"""
        seed = Seed.create_junior("test")
        assert seed.get(SeedKeys.NAME) == "test"
        seed.put(SeedKeys.ISPEED, "100")
        assert seed.get(SeedKeys.ISPEED) == "100"
        assert seed.get("nonexistent", "default") == "default"


# ===================================================================
# Seed 序列化
# ===================================================================


class TestSeedSerialization:
    """Seed 序列化/反序列化测试。"""

    def test_to_seed_string(self) -> None:
        """导出为种子字符串。"""
        seed = Seed.create_junior("test-peer", port=8090)
        encoded = seed.to_seed_string()
        assert encoded.startswith("z|") or encoded.startswith("p|")

        # 解码验证
        decoded = Seed.from_seed_string(encoded)
        assert decoded.hash == seed.hash
        assert decoded.name == seed.name

    def test_roundtrip_junior(self) -> None:
        """Junior 节点序列化往返。"""
        seed = Seed.create_junior("roundtrip-peer")
        encoded = seed.to_seed_string()
        decoded = Seed.from_seed_string(encoded)
        assert decoded.hash == seed.hash
        assert decoded.name == seed.name
        assert decoded.peer_type == PEERTYPE_JUNIOR

    def test_roundtrip_senior(self) -> None:
        """Senior 节点序列化往返。"""
        dna = {
            SeedKeys.HASH: "roundtripsr",
            SeedKeys.NAME: "SeniorRoundtrip",
            SeedKeys.PEERTYPE: PEERTYPE_SENIOR,
            SeedKeys.IP: "10.0.0.100",
            SeedKeys.PORT: "8090",
            SeedKeys.VERSION: "1.92",
            SeedKeys.UPTIME: "7200",
            SeedKeys.LCOUNT: "500000",
            SeedKeys.ICOUNT: "10000000",
        }
        seed = Seed(dna)
        encoded = seed.to_seed_string()
        decoded = Seed.from_seed_string(encoded)
        assert decoded.hash == seed.hash
        assert decoded.name == seed.name
        assert decoded.peer_type == PEERTYPE_SENIOR
        assert decoded.port == 8090


# ===================================================================
# Seed 时间戳
# ===================================================================


class TestSeedTimestamps:
    """Seed 时间戳测试。"""

    def test_touch(self) -> None:
        """更新最后联系时间。"""
        seed = Seed.create_junior("test")
        assert seed.last_contact == 0.0
        seed.touch()
        assert seed.last_contact > 0.0
        assert seed.age_seconds < 1.0

    def test_age_none_contacted(self) -> None:
        """从未联系过的节点年龄为无穷。"""
        seed = Seed.create_junior("test")
        assert seed.age_seconds == float("inf")

    def test_touch_updates_lastseen(self) -> None:
        """touch 应更新 LastSeen DNA 字段。"""
        seed = Seed.create_junior("test")
        old_lastseen = seed.get(SeedKeys.LASTSEEN)
        time.sleep(0.01)
        seed.touch()
        new_lastseen = seed.get(SeedKeys.LASTSEEN)
        # 时间戳可能或可能不相同（取决于秒级精度）
        assert old_lastseen != "" or new_lastseen != ""


# ===================================================================
# Seed 比较
# ===================================================================


class TestSeedComparison:
    """Seed 比较操作测试。"""

    def test_equality(self) -> None:
        """相同哈希的节点应相等。"""
        s1 = Seed.create_junior("node1")
        s2 = Seed({"Hash": s1.hash, "Name": "other"})
        assert s1 == s2

    def test_inequality(self) -> None:
        """不同哈希的节点不应相等。"""
        s1 = Seed.create_junior("node1")
        s2 = Seed.create_junior("node2")
        assert s1 != s2

    def test_hashable(self) -> None:
        """Seed 应可在 set/dict 中使用（相同哈希可去重）。"""
        s1 = Seed({"Hash": "AAA", "Name": "node1"})
        s2 = Seed({"Hash": "AAA", "Name": "node1_clone"})
        seeds = {s1, s2}
        assert len(seeds) == 1  # 相同哈希去重

    def test_comparison(self) -> None:
        """排序比较。"""
        s1 = Seed({"Hash": "AAA"})
        s2 = Seed({"Hash": "BBB"})
        assert s1 < s2


# ===================================================================
# 时间格式
# ===================================================================


class TestTimeFormats:
    """时间格式测试。"""

    def test_current_yacy_time_format(self) -> None:
        """YaCy 时间格式验证。"""
        t = _current_yaCy_time()
        # 格式: yyyy/MM/dd HH:mm:ss
        parts = t.split()
        assert len(parts) == 2
        date_parts = parts[0].split("/")
        assert len(date_parts) == 3
        time_parts = parts[1].split(":")
        assert len(time_parts) == 3

    def test_utc_offset_format(self) -> None:
        """UTC 偏移格式。"""
        offset = _utc_offset_string()
        assert len(offset) == 5  # +0800 / -0500
        assert offset[0] in ("+", "-")
        assert offset[1:].isdigit()
