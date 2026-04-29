# -*- coding: utf-8 -*-
"""PYaCy P2P 网络管理模块。

本模块是 PYaCy P2P 网络管理的核心协调层，负责：
- 管理本地节点（Junior）的生命周期
- 连接种子节点并引导入网
- 节点发现与路由表维护
- DHT 搜索的统一入口
- 处理无公网 IP 场景（默认 Junior 模式）

设计原则:
    - PYaCy 客户端默认为 Junior 节点（无公网端口）
    - 通过已有的 Public Seed 节点接入 P2P 网络
    - DHT 搜索通过 Senior 节点代理完成
    - 节点发现通过 Hello 协议和 seedlist 实现
    - 所有网络错误优雅降级，不阻塞主流程
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .dht.search import DHTSearchClient, DHTSearchResult
from .exceptions import PYaCyError, PYaCyP2PError
from .p2p.hello import HelloClient
from .p2p.protocol import P2PProtocol, DEFAULT_TIMEOUT, DEFAULT_NETWORK_NAME
from .p2p.seed import (
    PEERTYPE_JUNIOR,
    PEERTYPE_SENIOR,
    PEERTYPE_PRINCIPAL,
    Seed,
)
from .p2p.seeds import (
    build_seed_list,
    save_seed_cache,
    probe_seeds,
    fetch_online_seeds,
)

#: 日志记录器
_logger = logging.getLogger(__name__)

#: 已知的 YaCy Public Seed 节点（2026 年维护列表）。
#: 这些节点为 freeworld 网络中的稳定 Principal/Senior 节点。
#:
#: 注意: 实际种子管理已迁移到 ``pyacy.p2p.seeds`` 模块，
#: 使用 ``build_seed_list()`` 函数获取三层冗余的种子列表。
#: 此常量仅作为向后兼容保留。
DEFAULT_SEED_URLS: list[str] = [
    "http://yacy.searchlab.eu:8090",
]


class PYaCyNode:
    """PYaCy P2P 节点管理器。

    封装了 PYaCy 客户端作为 Junior 节点的完整生命周期，
    包括引导入网、节点发现、DHT 搜索等功能。

    **角色定位**: PYaCy 客户端最多作为 Junior 节点，
    通过已建立的 Public Seed/Senior 节点代理 DHT 搜索，
    不直接参与 RWI 索引分发。

    使用示例::

        # 创建 Junior 节点并引导入网
        node = PYaCyNode(name="my-pyacy")
        node.bootstrap()

        # DHT 搜索
        results = node.search("hello world", count=20)
        for ref in results.references:
            print(ref.title, ref.url)

        # 查看已知节点
        print(f"已知 {len(node.peers)} 个节点")
    """

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def __init__(
        self,
        *,
        name: str | None = None,
        port: int = 8090,
        timeout: int = DEFAULT_TIMEOUT,
        network_name: str = DEFAULT_NETWORK_NAME,
        seed_urls: list[str] | None = None,
    ):
        """初始化 PYaCy 节点。

        Args:
            name: 节点名称（可选，自动生成）。
            port: 本地端口标识（Junior 不绑定端口）。
            timeout: P2P 请求默认超时（秒）。
            network_name: 网络名称（默认 "freeworld"）。
            seed_urls: 自定义种子节点 URL 列表。
        """
        # 创建本地 Junior Seed
        self._my_seed: Seed = Seed.create_junior(name=name, port=port)

        # P2P 协议
        self._protocol: P2PProtocol = P2PProtocol(
            timeout=timeout,
            network_name=network_name,
        )

        # Hello 客户端
        self._hello: HelloClient = HelloClient(self._protocol)

        # DHT 搜索客户端
        self._search_client: DHTSearchClient = DHTSearchClient(self._protocol)

        # 节点发现状态
        self._peers: dict[str, Seed] = {}  # hash → Seed
        self._connected_seeds: set[str] = set()  # 已连接的种子哈希
        self._is_bootstrapped: bool = False
        self._bootstrap_time: float = 0.0
        self._seed_urls: list[str] = seed_urls or DEFAULT_SEED_URLS

        _logger.info("PYaCy 节点初始化: name=%s, hash=%s", self.name, self.hash)

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """节点名称。"""
        return self._my_seed.name

    @property
    def hash(self) -> str:
        """节点哈希。"""
        return self._my_seed.hash

    @property
    def my_seed(self) -> Seed:
        """本地节点 Seed。"""
        return self._my_seed

    @property
    def peers(self) -> dict[str, Seed]:
        """已知的远程节点（hash → Seed 映射）。"""
        return self._peers

    @property
    def peer_count(self) -> int:
        """已知节点总数。"""
        return len(self._peers)

    @property
    def senior_count(self) -> int:
        """可连接的 Senior 节点数。"""
        return sum(1 for s in self._peers.values() if s.is_reachable and s.is_senior())

    @property
    def is_bootstrapped(self) -> bool:
        """是否已完成网络引导。"""
        return self._is_bootstrapped

    @property
    def bootstrap_age(self) -> float:
        """距离上次引导的秒数。"""
        if self._bootstrap_time == 0:
            return float("inf")
        return time.time() - self._bootstrap_time

    # ------------------------------------------------------------------
    # 网络引导
    # ------------------------------------------------------------------

    def bootstrap(
        self,
        *,
        seed_urls: list[str] | None = None,
        max_peers: int = 100,
        rounds: int = 2,
        probe_timeout: float = 5.0,
    ) -> bool:
        """引导节点接入 P2P 网络。

        引导流程（v0.3.0 重写）：
        1. 使用 ``build_seed_list()`` 从三层来源获取候选种子
            （用户指定 → 本地缓存 → 硬编码种子）
        2. 并行探测候选种子的连通性
        3. 从可达种子获取 seedlist → 发现全部在线节点
        4. 向部分节点发送 Hello 请求（可选轮数）
        5. 将发现的节点持久化到本地缓存

        Args:
            seed_urls: 自定义种子节点 URL（覆盖默认值）。
            max_peers: 最大发现节点数。
            rounds: 节点发现轮数（Hello 扩展）。
            probe_timeout: 种子探测超时（秒）。

        Returns:
            True 如果至少连接到一个节点。
        """
        # 第一阶段：种子探测
        _logger.info("开始网络引导（v0.3.0 种子探测模式）...")

        # 准备候选种子
        custom_seeds: list[Seed] | None = None
        if seed_urls:
            custom_seeds = []
            for url in seed_urls:
                try:
                    s = Seed.create_junior(name=f"seed-{len(custom_seeds)}")
                    s.dna[SeedKeys.IP] = url.split("://")[1].split(":")[0] if "://" in url else url
                    s.dna[SeedKeys.PORT] = url.rsplit(":", 1)[1] if ":" in url.rsplit("://", 1)[-1] else "8090"
                    custom_seeds.append(s)
                except Exception:
                    pass

        # 使用种子管理系统获取可达种子
        try:
            reachable_seeds = build_seed_list(
                custom_seeds=custom_seeds,
                probe=True,
                probe_timeout=probe_timeout,
            )
        except Exception as exc:
            _logger.error("种子探测异常: %s", exc)
            self._is_bootstrapped = False
            return False

        if not reachable_seeds:
            _logger.error("种子探测失败: 无可用种子节点")
            self._is_bootstrapped = False
            return False

        _logger.info("种子探测完成: %d 个可达种子", len(reachable_seeds))

        # 第二阶段：从可达种子获取在线节点列表
        entry_urls = [s.base_url for s in reachable_seeds if s.base_url]
        entry_urls = [u for u in entry_urls if u]  # type narrowing

        online_seeds = fetch_online_seeds(entry_urls, timeout=probe_timeout)
        if online_seeds:
            _logger.info("在线发现 %d 个节点", len(online_seeds))
        else:
            # 在线获取失败时，直接使用可达种子
            online_seeds = list(reachable_seeds)
            _logger.info("在线获取失败，使用可达种子池: %d 个", len(online_seeds))

        # 将发现的节点加入已知列表
        new_count = 0
        for seed in online_seeds:
            if seed.hash != self.hash and seed.hash not in self._peers:
                self._peers[seed.hash] = seed
                new_count += 1

        # 第三阶段（可选）：Hello 扩展（在已发现的 Senior 节点间扩散）
        if rounds > 1 and new_count > 0:
            try:
                # 取可达种子 URL 作为发现入口
                seed_url_list = [s.base_url for s in reachable_seeds[:5] if s.base_url]
                more_discovered = self._hello.discover_network(
                    seed_urls=seed_url_list,
                    my_seed=self._my_seed,
                    max_peers=max_peers,
                    rounds=rounds - 1,
                )
                for seed in more_discovered:
                    if seed.hash != self.hash and seed.hash not in self._peers:
                        self._peers[seed.hash] = seed
                        new_count += 1
                _logger.info("Hello 扩展: 额外发现 %d 个节点", len(more_discovered))
            except Exception as exc:
                _logger.debug("Hello 扩展跳过: %s", exc)

        self._is_bootstrapped = len(self._peers) > 0
        self._bootstrap_time = time.time()

        # 持久化种子缓存
        if self._is_bootstrapped:
            try:
                save_seed_cache(list(self._peers.values()))
            except Exception as exc:
                _logger.debug("种子缓存保存失败: %s", exc)

        _logger.info(
            "网络引导完成: 发现 %d 个新节点（共 %d 个），%d 个 Senior",
            new_count, len(self._peers), self.senior_count,
        )

        return self._is_bootstrapped

    # ------------------------------------------------------------------
    # Hello 连通性检查
    # ------------------------------------------------------------------

    def hello_peer(self, target: Seed) -> dict[str, Any] | None:
        """向单个远程节点发送 Hello 请求。

        Args:
            target: 目标节点。

        Returns:
            Hello 响应字典，失败返回 None。
        """
        if not target.base_url:
            _logger.debug("节点 %s 无可用 URL", target.name)
            return None

        result = self._hello.hello_peer(
            target_url=target.base_url,
            target_hash=target.hash,
            my_seed=self._my_seed,
        )

        if result.success:
            target.touch()
            # 将响应中的种子加入已知列表
            for seed in result.seeds:
                if seed.hash not in self._peers and seed.hash != self.hash:
                    self._peers[seed.hash] = seed

            return {
                "success": True,
                "your_ip": result.your_ip,
                "your_type": result.your_type,
                "seeds_received": len(result.seeds),
            }

        return None

    def ping_peers(self, *, max_peers: int = 10) -> list[dict[str, Any]]:
        """向部分已知节点发送 Hello（保活）。

        Args:
            max_peers: 最多 PING 的节点数。

        Returns:
            各节点的 Hello 结果列表。
        """
        reachable = [
            s for s in self._peers.values()
            if s.base_url and s.hash != self.hash
        ]

        # 优先 PING 最近未联系的 Senior 节点
        reachable.sort(key=lambda s: s.age_seconds)
        targets = reachable[:max_peers]

        results: list[dict[str, Any]] = []
        for target in targets:
            result = self.hello_peer(target)
            if result:
                results.append({
                    "peer": target.name,
                    "hash": target.hash,
                    **result,
                })

        _logger.info("PING %d 个节点，成功 %d 个", len(targets), len(results))
        return results

    # ------------------------------------------------------------------
    # DHT 搜索
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        count: int = 20,
        max_peers: int = 20,
        iterative: bool = True,
        language: str = "",
        exclude_words: list[str] | None = None,
        **kwargs: Any,
    ) -> DHTSearchResult:
        """执行 DHT 全文搜索（v0.3.0：哈希路由）。

        使用 DHT 哈希路由选择负责节点，而非随机选取。
        若首轮无结果，自动扩大搜索范围（迭代扩展）。

        Args:
            query: 搜索查询字符串。
            count: 期望结果数（默认 20）。
            max_peers: 每轮最多搜索的节点数（默认 20，v0.2.x 为 5）。
            iterative: 是否启用迭代扩展（默认 True）。
            language: 语言过滤（如 "zh", "en"）。
            exclude_words: 排除词列表。
            **kwargs: 其他搜索参数。

        Returns:
            DHTSearchResult 实例。

        Raises:
            PYaCyP2PError: 如果没有可连接的节点。
        """
        if not self._peers:
            raise PYaCyP2PError(
                "无可用于搜索的节点。请先调用 bootstrap() 引导入网。"
            )

        result = self._search_client.fulltext_search(
            peers=list(self._peers.values()),
            my_hash=self.hash,
            query=query,
            count=count,
            max_peers=max_peers,
            iterative=iterative,
            language=language,
            exclude_words=exclude_words,
            **kwargs,
        )

        return result

    def search_on_peer(
        self,
        target: Seed,
        query: str,
        *,
        count: int = 10,
        **kwargs: Any,
    ) -> DHTSearchResult:
        """在指定节点上执行 DHT 搜索。

        Args:
            target: 目标节点。
            query: 搜索查询。
            count: 期望结果数。
            **kwargs: 其他搜索参数。

        Returns:
            DHTSearchResult 实例。
        """
        if not target.base_url:
            raise PYaCyP2PError(f"节点 {target.name} 无可用 URL")

        return self._search_client.search(
            target_url=target.base_url,
            target_hash=target.hash,
            my_hash=self.hash,
            query=query,
            count=count,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # 节点管理
    # ------------------------------------------------------------------

    def add_peer(self, url: str, seed_str: str) -> Seed | None:
        """手动添加一个节点。

        Args:
            url: 节点 URL。
            seed_str: 种子字符串。

        Returns:
            添加的 Seed，或 None（如果解析失败）。
        """
        try:
            seed = Seed.from_seed_string(seed_str)
            if seed.hash not in self._peers and seed.hash != self.hash:
                self._peers[seed.hash] = seed
                _logger.info("手动添加节点: %s (%s)", seed.name, seed.hash[:8])
                return seed
        except Exception as exc:
            _logger.warning("解析种子失败: %s", exc)
        return None

    def remove_peer(self, peer_hash: str) -> bool:
        """移除一个已知节点。

        Args:
            peer_hash: 节点哈希。

        Returns:
            True 如果节点存在于已知列表中并被移除。
        """
        if peer_hash in self._peers:
            del self._peers[peer_hash]
            return True
        return False

    def get_peer(self, peer_hash: str) -> Seed | None:
        """根据哈希获取节点。

        Args:
            peer_hash: 节点哈希。

        Returns:
            Seed 或 None。
        """
        return self._peers.get(peer_hash)

    def get_senior_peers(self) -> list[Seed]:
        """获取所有可连接的 Senior 节点。

        Returns:
            Senior 节点列表。
        """
        return [
            s for s in self._peers.values()
            if s.is_reachable and s.is_senior()
        ]

    def get_peer_stats(self) -> dict[str, Any]:
        """获取节点池统计信息。

        Returns:
            包含计数和分布信息的字典。
        """
        types: dict[str, int] = {}
        for seed in self._peers.values():
            pt = seed.peer_type
            types[pt] = types.get(pt, 0) + 1

        return {
            "total_peers": len(self._peers),
            "senior_peers": self.senior_count,
            "junior_peers": types.get(PEERTYPE_JUNIOR, 0),
            "principal_peers": types.get(PEERTYPE_PRINCIPAL, 0),
            "is_bootstrapped": self._is_bootstrapped,
            "my_hash": self.hash,
            "my_name": self.name,
            "type_distribution": types,
        }

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------

    def close(self) -> None:
        """关闭节点，清理资源。

        当前实现仅清理内存中的节点池。
        """
        self._peers.clear()
        self._is_bootstrapped = False
        _logger.info("PYaCy 节点已关闭: %s", self.name)

    def __enter__(self) -> "PYaCyNode":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"PYaCyNode(name={self.name!r}, peers={len(self._peers)}, "
            f"seniors={self.senior_count}, bootstrapped={self._is_bootstrapped})"
        )
