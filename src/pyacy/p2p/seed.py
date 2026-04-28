# -*- coding: utf-8 -*-
"""PYaCy P2P 种子（Peer）模块。

本模块实现了 YaCy 节点的表示与管理，包括：
- 种子字符串编解码
- 节点属性管理（DNA 映射）
- 节点类型常量
- 节点可达性判断

设计原则:
    - 纯 Python 标准库实现，零外部依赖
    - 完全兼容 YaCy Java 版本的种子格式
    - PYaCy 客户端默认为 Junior 节点
"""

from __future__ import annotations

import time
from typing import Any

from ..utils import (
    WORD_HASH_LENGTH,
    compute_peer_hash,
    decode_seed_string,
    encode_seed_string,
)


# ---------------------------------------------------------------------------
# 节点类型常量
# ---------------------------------------------------------------------------

#: 初始节点 — 刚启动，尚未连接到任何节点
PEERTYPE_VIRGIN: str = "virgin"

#: 初级节点 — 无公网可达端口，无法被其他节点主动连接
PEERTYPE_JUNIOR: str = "junior"

#: 高级节点 — 有公网可达端口，可被主动连接并提供搜索服务
PEERTYPE_SENIOR: str = "senior"

#: 主节点 — Senior 节点的特例，同时分发种子列表
PEERTYPE_PRINCIPAL: str = "principal"

#: 学徒节点 — 有 Mentor 节点的 Junior
PEERTYPE_MENTEE: str = "mentee"

#: 导师节点 — 为 Mentee 提供端口的 Senior
PEERTYPE_MENTOR: str = "mentor"

#: 所有有效的节点类型
VALID_PEERTYPES: frozenset[str] = frozenset({
    PEERTYPE_VIRGIN,
    PEERTYPE_JUNIOR,
    PEERTYPE_SENIOR,
    PEERTYPE_PRINCIPAL,
    PEERTYPE_MENTEE,
    PEERTYPE_MENTOR,
})


# ---------------------------------------------------------------------------
# 种子属性键名常量
# ---------------------------------------------------------------------------

class SeedKeys:
    """种子 DNA 字典中的键名常量。

    与 YaCy Java 的 ``Seed.java`` 保持一致。
    """

    # 身份
    HASH: str = "Hash"
    NAME: str = "Name"
    PEERTYPE: str = "PeerType"
    VERSION: str = "Version"
    FLAGS: str = "Flags"
    TAGS: str = "Tags"

    # 网络
    IP: str = "IP"
    IP6: str = "IP6"
    PORT: str = "Port"
    PORTSSL: str = "PortSSL"
    SEEDLISTURL: str = "seedURL"

    # 时间
    LASTSEEN: str = "LastSeen"
    BDATE: str = "BDate"
    UTC: str = "UTC"
    DCT: str = "dct"  # disconnect time

    # 统计
    ISPEED: str = "ISpeed"    # 索引速度（页/分钟）
    RSPEED: str = "RSpeed"    # 检索速度（查询/分钟）
    USPEED: str = "USpeed"    # 上行速度
    UPTIME: str = "Uptime"    # 运行时间（分钟/天）
    LCOUNT: str = "LCount"    # 已存储链接数
    NCOUNT: str = "NCount"    # 已发现但未加载链接数
    RCOUNT: str = "RCount"    # 供远程爬取的链接数
    ICOUNT: str = "ICount"    # 已索引不同单词数
    SCOUNT: str = "SCount"    # 已存储种子数
    CCOUNT: str = "CCount"    # 客户端连接数

    # 索引传输
    INDEX_OUT: str = "sI"    # 已发送索引
    INDEX_IN: str = "rI"     # 已接收索引
    URL_OUT: str = "sU"      # 已发送 URL
    URL_IN: str = "rU"       # 已接收 URL

    # Hello 响应
    YOURTYPE: str = "yourtype"
    NEWS: str = "news"
    SOLRAVAILABLE: str = "SorlAvail"


# ---------------------------------------------------------------------------
# Seed 类
# ---------------------------------------------------------------------------


class Seed:
    """YaCy P2P 网络中的节点。

    每个 Seed 代表 P2P 网络中的一个已知节点，包含其网络地址、
    节点类型、能力标识等属性（称为 DNA）。

    Attributes:
        dna: 节点属性字典（DNA 映射）。
        hash: 节点唯一哈希值。
    """

    # ------------------------------------------------------------------
    # 静态工厂方法
    # ------------------------------------------------------------------

    @staticmethod
    def create_junior(name: str | None = None, port: int = 8090) -> "Seed":
        """创建一个 Junior 类型的本地节点。

        Junior 节点假设自己没有公网 IP，无法被其他节点主动连接。

        Args:
            name: 节点名称（可选，自动生成）。
            port: 本地监听端口（仅用于标识，Junior 节点不需要公网端口）。

        Returns:
            新创建的 Seed 实例。
        """
        if name is None:
            name = f"pyacy-junior-{int(time.time()) % 100000}"

        identity = f"{name}:{port}:{time.time()}"
        peer_hash = compute_peer_hash(identity)

        dna: dict[str, str] = {
            SeedKeys.HASH: peer_hash,
            SeedKeys.NAME: name,
            SeedKeys.PEERTYPE: PEERTYPE_JUNIOR,
            SeedKeys.PORT: str(port),
            SeedKeys.IP: "",
            SeedKeys.IP6: "",
            SeedKeys.VERSION: "0.2.3",
            SeedKeys.FLAGS: "    ",
            SeedKeys.ISPEED: "0",
            SeedKeys.RSPEED: "0",
            SeedKeys.UPTIME: "0",
            SeedKeys.LCOUNT: "0",
            SeedKeys.NCOUNT: "0",
            SeedKeys.RCOUNT: "0",
            SeedKeys.ICOUNT: "0",
            SeedKeys.SCOUNT: "0",
            SeedKeys.CCOUNT: "0",
            SeedKeys.INDEX_OUT: "0",
            SeedKeys.INDEX_IN: "0",
            SeedKeys.URL_OUT: "0",
            SeedKeys.URL_IN: "0",
            SeedKeys.UTC: _utc_offset_string(),
            SeedKeys.BDATE: _current_yaCy_time(),
            SeedKeys.LASTSEEN: _current_yaCy_time(),
        }
        return Seed(dna)

    @staticmethod
    def from_seed_string(seed_str: str, *, default_ip: str | None = None) -> "Seed":
        """从 YaCy 种子字符串创建 Seed。

        支持简单格式（``p|{...}``）和压缩格式（``z|...``）。

        Args:
            seed_str: YaCy 种子字符串。
            default_ip: 若种子字符串不含 IP，使用此默认 IP。

        Returns:
            解析后的 Seed 实例。

        Raises:
            ValueError: 种子字符串格式无效。
        """
        dna = decode_seed_string(seed_str)

        # 如果种子没有 IP 但有默认 IP，则补充
        if default_ip and not dna.get(SeedKeys.IP):
            dna[SeedKeys.IP] = default_ip

        # 确保必要字段存在
        dna.setdefault(SeedKeys.PEERTYPE, PEERTYPE_JUNIOR)
        dna.setdefault(SeedKeys.NAME, "unknown")

        return Seed(dna)

    @staticmethod
    def from_json(data: dict[str, Any]) -> "Seed":
        """从 JSON 字典创建 Seed（用于 seedlist.json 端点）。

        YaCy 的 seedlist.json 端点直接返回种子 DNA 字段，
        键名与 SeedKeys 常量一致（如 "Hash"、"PeerType"、"IP" 等），
        因此可以直接复用到 dna 字典中。

        特殊处理:
            - "Address" 字段是数组（如 ``["ip:port"]``），用于补充 IP。
            - 某些旧版 YaCy 可能返回小写键名，这里也兼容处理。

        Args:
            data: seedlist.json 中的种子条目。

        Returns:
            Seed 实例。
        """
        dna: dict[str, str] = {}

        # 直接复用 YaCy 原生的 DNA 键名到 dna 字典
        for key, value in data.items():
            if key == "Address":
                # Address 是 ["ip:port", ...] 数组。
                # 仅当 JSON 中未提供 IP 字段时，才从 Address 中提取。
                if SeedKeys.IP not in dna and isinstance(value, list) and value:
                    addr = str(value[0])
                    # 处理 IPv6 地址（如 "[::1]:8090"）
                    if addr.startswith("[") and "]" in addr:
                        ip = addr[1:addr.index("]")]
                    elif ":" in addr:
                        # IPv4 或纯 IPv6（无括号）
                        ip = addr.rsplit(":", 1)[0]
                    else:
                        ip = addr
                    if ip:
                        dna[SeedKeys.IP] = ip
                continue
            if key in ("news",):
                continue  # 跳过无意义字段
            if value is not None:
                dna[key] = str(value)

        # 确保必要字段存在
        dna.setdefault(SeedKeys.PEERTYPE, PEERTYPE_JUNIOR)
        dna.setdefault(SeedKeys.NAME, data.get("Name", data.get("name", "unknown")))
        dna.setdefault(SeedKeys.PORT, "8090")

        return Seed(dna)

    # ------------------------------------------------------------------
    # 构造函数
    # ------------------------------------------------------------------

    def __init__(self, dna: dict[str, str]):
        """初始化 Seed。

        Args:
            dna: 节点属性字典。必须包含 ``Hash`` 键。
        """
        self.dna: dict[str, str] = dict(dna)
        self.hash: str = dna.get(SeedKeys.HASH, "")
        self._last_contact: float = 0.0

    # ------------------------------------------------------------------
    # 属性访问
    # ------------------------------------------------------------------

    def get(self, key: str, default: str = "") -> str:
        """安全获取 DNA 属性值。

        Args:
            key: 属性键名。
            default: 默认值。

        Returns:
            属性值或默认值。
        """
        return self.dna.get(key, default)

    def put(self, key: str, value: str) -> None:
        """设置 DNA 属性值。

        Args:
            key: 属性键名。
            value: 属性值。
        """
        self.dna[key] = value

    @property
    def name(self) -> str:
        """节点名称。"""
        return self.get(SeedKeys.NAME, "unknown")

    @property
    def peer_type(self) -> str:
        """节点类型（virgin/junior/senior/principal）。"""
        return self.get(SeedKeys.PEERTYPE, PEERTYPE_VIRGIN)

    @property
    def ip(self) -> str | None:
        """节点的首选公网 IP。"""
        ip_val = self.get(SeedKeys.IP, "")
        return ip_val if ip_val else None

    @property
    def port(self) -> int:
        """节点 HTTP 端口。"""
        try:
            return int(self.get(SeedKeys.PORT, "0"))
        except ValueError:
            return 0

    @property
    def version(self) -> str:
        """节点 YaCy 版本。"""
        return self.get(SeedKeys.VERSION, "0.0.0")

    @property
    def uptime_minutes(self) -> int:
        """节点运行时间（分钟）。"""
        try:
            return int(self.get(SeedKeys.UPTIME, "0"))
        except ValueError:
            return 0

    # ------------------------------------------------------------------
    # 类型判断
    # ------------------------------------------------------------------

    def is_junior(self) -> bool:
        """判断是否为 Junior 节点。"""
        return self.peer_type == PEERTYPE_JUNIOR

    def is_senior(self) -> bool:
        """判断是否为 Senior 节点。"""
        return self.peer_type in (PEERTYPE_SENIOR, PEERTYPE_PRINCIPAL, PEERTYPE_MENTOR)

    def is_principal(self) -> bool:
        """判断是否为 Principal 节点。"""
        return self.peer_type == PEERTYPE_PRINCIPAL

    def is_virgin(self) -> bool:
        """判断是否为 Virgin 节点。"""
        return self.peer_type == PEERTYPE_VIRGIN

    # ------------------------------------------------------------------
    # 可达性
    # ------------------------------------------------------------------

    @property
    def base_url(self) -> str | None:
        """节点的 HTTP 基础 URL。

        仅当节点有有效 IP 和端口时返回。
        自动处理 IPv6 地址（添加方括号）。

        Returns:
            ``http://ip:port`` 格式的 URL，或 None。
        """
        ip_val = self.ip
        if not ip_val or self.port == 0:
            return None
        # IPv6 地址需要用方括号包裹
        if ":" in ip_val and not ip_val.startswith("["):
            ip_val = f"[{ip_val}]"
        return f"http://{ip_val}:{self.port}"

    @property
    def is_reachable(self) -> bool:
        """判断节点是否可被连接。

        Junior 节点默认不可被主动连接。
        Senior/Principal 节点若有 IP 和端口则可连接。

        Returns:
            True 如果节点可被连接。
        """
        if self.is_junior() or self.is_virgin():
            return False
        return self.base_url is not None

    # ------------------------------------------------------------------
    # 种子字符串
    # ------------------------------------------------------------------

    def to_seed_string(self, *, salt: str = "", compress: bool = False) -> str:
        """将 Seed 导出为 YaCy 种子字符串。

        **重要**: P2P 通信默认使用未压缩格式（``p|{...}``），
        因为 Python ``gzip.compress()`` 与 Java ``GZIPInputStream`` 不兼容，
        压缩后的种子会导致 YaCy 服务器返回 ``bad seed: seed == null``。

        Args:
            salt: 加密盐（用于安全传输）。
            compress: 是否使用 gzip 压缩。默认 False（P2P 兼容模式）。

        Returns:
            编码后的种子字符串。
        """
        return encode_seed_string(self.dna, compress=compress)

    # ------------------------------------------------------------------
    # 时间戳
    # ------------------------------------------------------------------

    def touch(self) -> None:
        """更新最后联系时间戳。"""
        self._last_contact = time.time()
        self.dna[SeedKeys.LASTSEEN] = _current_yaCy_time()

    @property
    def last_contact(self) -> float:
        """最后联系时间（Unix 时间戳）。"""
        return self._last_contact

    @property
    def age_seconds(self) -> float:
        """距上次联系的秒数。"""
        if self._last_contact == 0:
            return float("inf")
        return time.time() - self._last_contact

    # ------------------------------------------------------------------
    # 魔术方法
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"Seed(name={self.name!r}, type={self.peer_type!r}, "
            f"hash={self.hash[:8]}...)"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Seed):
            return NotImplemented
        return self.hash == other.hash

    def __hash__(self) -> int:
        return hash(self.hash)

    def __lt__(self, other: "Seed") -> bool:
        return self.hash < other.hash


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _current_yaCy_time() -> str:
    """生成 YaCy 格式的当前时间字符串。

    YaCy 使用 ``yyyy/MM/dd HH:mm:ss`` 格式。

    Returns:
        格式化的时间字符串。
    """
    return time.strftime("%Y/%m/%d %H:%M:%S", time.localtime())


def _utc_offset_string() -> str:
    """生成 UTC 偏移字符串。

    Returns:
        如 ``+0800`` 格式的偏移字符串。
    """
    offset = time.timezone if not time.localtime().tm_isdst else time.altzone
    sign = "-" if offset > 0 else "+"
    hours = abs(offset) // 3600
    minutes = (abs(offset) % 3600) // 60
    return f"{sign}{hours:02d}{minutes:02d}"
