# -*- coding: utf-8 -*-
"""PYaCy Pull 模式 RWI 拉取器。

本模块实现了 PYaCy 节点的 Pull 模式，使无公网 IP 的 Junior 节点
也能主动获取 RWI 数据，而不依赖被动接收 Push。

Pull 模式原理:
    传统 YaCy 网络中，RWI 由 Senior 节点通过 Push 模式分发：
        Senior A → 计算词哈希 → 找到负责节点 B → Push RWI 到 B

    Pull 模式反转了这个过程：
        Junior C → 主动向 Senior 节点查询特定词哈希的 RWI
                 → 将查询结果存储到本地 RWI 存储

    Pull 模式的优势:
    1. 无需公网 IP（Junior 发起传出连接即可）
    2. 无需 Senior 节点的特殊配合（复用现有搜索端点）
    3. 渐进式积累本地索引

Pull 策略:
    1. 从本地已有词哈希出发，扩展相关 RWI
    2. 使用高频英文词哈希作为种子（如 "the", "and", "of"）
    3. 从搜索结果中提取新的词哈希，形成 Pull 链
    4. 定期执行，渐进式丰富本地索引

设计原则:
    - 纯 Python 标准库实现
    - 不需要 Senior 节点的特殊配合
    - 可配置的 Pull 频率和批量大小
    - 自动限速，避免对远程节点造成压力

使用示例::

    from pyacy.rwi import RWIStorage, RWIPuller
    from pyacy import PYaCyNode

    node = PYaCyNode(name="my-pyacy")
    node.bootstrap()

    storage = RWIStorage("~/.pyacy/rwi.db")
    puller = RWIPuller(node, storage)

    # 执行一次 Pull
    imported = puller.pull_once()

    # 启动定期 Pull（后台线程）
    puller.start_periodic_pull(interval=300)

    # 停止定期 Pull
    puller.stop_periodic_pull()
"""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any

from ..p2p.seed import Seed
from ..utils import word_to_hash, dht_distance
from .storage import RWIEntry, RWIStorage

#: 日志记录器
_logger = logging.getLogger(__name__)

#: Pull 模式默认参数
DEFAULT_PULL_INTERVAL: int = 300      # Pull 间隔（秒，默认 5 分钟）
DEFAULT_PULL_PEERS: int = 10          # 每次 Pull 选择的节点数
DEFAULT_PULL_WORDS: int = 8           # 每次 Pull 的词哈希数
DEFAULT_PULL_COUNT: int = 20          # 每次查询期望的结果数
DEFAULT_PULL_TIMEOUT_MS: int = 10000  # 单次查询超时（毫秒）

# 高频英文种子词（用于初始 Pull）
# 这些词在英文网页中出现频率极高，几乎所有 Senior 节点都有相关 RWI。
# 选择这些词作为 Pull 种子，可以快速积累初始索引。
_SEED_WORDS_EN: list[str] = [
    "the", "and", "of", "to", "in", "for", "is", "on",
    "with", "that", "this", "are", "be", "was", "have",
    "python", "java", "linux", "open", "source", "code",
    "search", "web", "data", "system", "network", "server",
    "http", "www", "com", "org", "net", "html", "page",
]

# 高频中文种子词（UTF-8 编码后的哈希）
# 注意：中文词在 YaCy 网络中的 RWI 覆盖率较低，
# 但随着 PYaCy 的发展，这些词的覆盖率会逐步提高。
_SEED_WORDS_ZH: list[str] = [
    "的", "是", "在", "了", "不", "和", "有", "人",
    "这", "中", "大", "为", "上", "个", "到", "说",
    "搜索", "网络", "数据", "系统", "服务器",
]


class RWIPuller:
    """RWI Pull 模式拉取器。

    通过复用现有的 DHT 搜索端点，主动从 Senior 节点拉取 RWI 数据。
    无需 Senior 节点的特殊配合，也无需本地节点有公网 IP。

    Pull 策略说明:
        Pull 模式不是"从某个固定端点拉取 RWI"，
        而是"向 Senior 节点发送搜索请求，将搜索结果存储为本地 RWI"。

        具体流程:
        1. 选择一组词哈希（来自种子词或本地已有词哈希）
        2. 将这些词哈希作为搜索查询发送给 Senior 节点
        3. Senior 节点在本地 RWI 中查找匹配，返回结果
        4. 将结果解析为 RWIEntry 并存入本地存储

        这样做的好处:
        - 复用现有协议，无需新增端点
        - Senior 节点无需任何修改
        - 渐进式积累，不会对网络造成冲击

    使用示例::

        puller = RWIPuller(node, storage)

        # 单次 Pull
        imported = puller.pull_once()

        # 后台定期 Pull
        puller.start_periodic_pull(interval=300)
        # ... 其他操作 ...
        puller.stop_periodic_pull()
    """

    def __init__(
        self,
        node: Any,  # PYaCyNode（避免循环导入）
        storage: RWIStorage,
        *,
        pull_interval: int = DEFAULT_PULL_INTERVAL,
        pull_peers: int = DEFAULT_PULL_PEERS,
        pull_words: int = DEFAULT_PULL_WORDS,
        pull_count: int = DEFAULT_PULL_COUNT,
        pull_timeout_ms: int = DEFAULT_PULL_TIMEOUT_MS,
    ):
        """初始化 Pull 拉取器。

        Args:
            node: PYaCyNode 实例（需要已 bootstrap）。
            storage: RWIStorage 实例。
            pull_interval: 定期 Pull 的间隔（秒）。
            pull_peers: 每次 Pull 选择的节点数。
            pull_words: 每次 Pull 的词哈希数。
            pull_count: 每次查询期望的结果数。
            pull_timeout_ms: 单次查询超时（毫秒）。
        """
        self._node = node
        self._storage = storage
        self._interval = pull_interval
        self._peers_count = pull_peers
        self._words_count = pull_words
        self._count = pull_count
        self._timeout_ms = pull_timeout_ms

        # 后台 Pull 线程控制
        self._pull_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Pull 统计
        self._total_pulled: int = 0
        self._total_pulls: int = 0
        self._last_pull_time: float = 0.0

    # ------------------------------------------------------------------
    # 单次 Pull
    # ------------------------------------------------------------------

    def pull_once(self, *, word_hashes: list[str] | None = None) -> int:
        """执行一次 Pull 操作。

        流程:
        1. 选择词哈希（用户指定或自动选择）
        2. 选择目标 Senior 节点
        3. 向每个节点发送搜索请求
        4. 将结果解析为 RWI 并存入本地存储

        Args:
            word_hashes: 自定义词哈希列表（可选）。
                None 时自动选择词哈希。

        Returns:
            本次 Pull 导入的 RWI 条目数。
        """
        if not self._node.is_bootstrapped:
            _logger.warning("Pull 失败: 节点未 bootstrap")
            return 0

        # 1. 选择词哈希
        if word_hashes is None:
            word_hashes = self._select_word_hashes()

        if not word_hashes:
            _logger.debug("Pull 跳过: 无可选词哈希")
            return 0

        # 2. 选择目标 Senior 节点
        targets = self._select_targets()
        if not targets:
            _logger.warning("Pull 失败: 无可连接的 Senior 节点")
            return 0

        # 3. 向每个节点发送搜索请求并收集 RWI
        #    旧逻辑在第一个词哈希返回 0 条时就跳过该节点的所有剩余词哈希，
        #    但这会导致节点只因一个词没有 RWI 就被完全跳过。
        #    不同词的 RWI 存储是独立的，一个词没结果不代表其他词也没有。
        total_imported = 0
        consecutive_failures = 0  # 连续失败计数器
        for target in targets:
            consecutive_failures = 0
            for word_hash in word_hashes:
                # 连续 2 次失败才跳过该节点（而非 1 次就跳过）
                if consecutive_failures >= 2:
                    _logger.debug(
                        "Pull 跳过节点 %s（连续 %d 次失败）",
                        target.name, consecutive_failures,
                    )
                    break
                try:
                    imported = self._pull_from_peer(target, word_hash)
                    total_imported += imported
                    if imported == 0:
                        consecutive_failures += 1
                    else:
                        consecutive_failures = 0  # 成功则重置
                except Exception as exc:
                    consecutive_failures += 1
                    _logger.debug(
                        "Pull 异常 (%s, %s): %s",
                        target.name, word_hash[:8], exc,
                    )

        # 更新统计
        self._total_pulled += total_imported
        self._total_pulls += 1
        self._last_pull_time = time.time()

        _logger.info(
            "Pull 完成: 导入 %d 条 RWI（词哈希=%d, 节点=%d）",
            total_imported, len(word_hashes), len(targets),
        )

        return total_imported

    def _pull_from_peer(self, target: Seed, word_hash: str) -> int:
        """从单个节点拉取指定词哈希的 RWI。

        通过 DHT 搜索端点发送查询，将结果解析为 RWI 条目。

        Args:
            target: 目标 Senior 节点。
            word_hash: 要查询的词哈希。

        Returns:
            导入的 RWI 条目数。
        """
        protocol = self._node._protocol

        # 发送搜索请求
        response = protocol.search(
            target_url=target.base_url,
            target_hash=target.hash,
            my_hash=self._node.hash,
            query_hashes=word_hash,
            count=self._count,
            max_time=self._timeout_ms,
            abstracts="",
        )

        # 解析响应中的 resourceN 字段
        imported = 0
        data = response.data

        # 从 resource0, resource1, ... 中提取 RWI
        i = 0
        while True:
            resource_key = f"resource{i}"
            resource_str = data.get(resource_key, "")
            if not resource_str:
                break

            try:
                entry = self._parse_resource_to_rwi(word_hash, resource_str)
                if entry and self._storage.insert(entry):
                    imported += 1
            except Exception as exc:
                _logger.debug("RWI 解析失败 (resource%d): %s", i, exc)

            i += 1

        return imported

    def _parse_resource_to_rwi(
        self,
        word_hash: str,
        resource_str: str,
    ) -> RWIEntry | None:
        """将 resource 字符串解析为 RWIEntry。

        Args:
            word_hash: 词哈希。
            resource_str: YaCy resource 字段的原始字符串。

        Returns:
            RWIEntry 实例，解析失败返回 None。
        """
        from ..dht.search import _parse_resources
        from ..p2p.protocol import P2PResponse

        # 创建临时 P2PResponse 来复用解析逻辑
        temp_response = P2PResponse("")
        temp_response.data["resource0"] = resource_str

        refs, links = _parse_resources(temp_response.data)
        if not refs:
            return None

        ref = refs[0]
        return RWIEntry(
            word_hash=word_hash,
            url_hash=ref.url_hash,
            url=ref.url,
            title=ref.title,
            description=ref.description,
            size=ref.size,
            word_count=ref.word_count,
            last_modified=ref.last_modified,
            language=ref.language,
        )

    # ------------------------------------------------------------------
    # 词哈希选择策略
    # ------------------------------------------------------------------

    def _select_word_hashes(self) -> list[str]:
        """选择本次 Pull 的词哈希。

        策略:
        1. 70% 概率从种子词中选择（保证覆盖常见词）
        2. 30% 概率从本地已有词哈希中选择（扩展相关 RWI）

        Returns:
            词哈希列表。
        """
        hashes: list[str] = []
        seen: set[str] = set()

        # 从种子词中选择
        seed_count = max(1, int(self._words_count * 0.7))
        all_seed_words = _SEED_WORDS_EN + _SEED_WORDS_ZH
        random.shuffle(all_seed_words)

        for word in all_seed_words[:seed_count]:
            h = word_to_hash(word)
            if h not in seen:
                seen.add(h)
                hashes.append(h)

        # 从本地已有词哈希中选择（扩展）
        local_count = self._words_count - len(hashes)
        if local_count > 0:
            local_hashes = self._storage.get_random_word_hashes(local_count)
            for h in local_hashes:
                if h not in seen:
                    seen.add(h)
                    hashes.append(h)

        random.shuffle(hashes)
        return hashes[:self._words_count]

    # ------------------------------------------------------------------
    # 节点选择策略
    # ------------------------------------------------------------------

    def _select_targets(self) -> list[Seed]:
        """选择本次 Pull 的目标节点。

        策略:
        1. 使用词哈希的 DHT 路由找到负责节点（而非随机选择）
        2. 随机打乱以避免总是查询同一批节点

        这确保了 Pull 请求发往真正拥有该词 RWI 的节点，大幅提高命中率。

        Returns:
            目标 Seed 列表。
        """
        from ..dht.search import _find_responsible_peers

        reachable = [
            s for s in self._node._peers.values()
            if s.is_reachable and s.is_senior() and s.base_url
        ]

        if not reachable:
            return []

        # 使用 DHT 哈希路由找到对种子词负责的节点
        # 生成一批种子词哈希用于路由
        all_seed_words = _SEED_WORDS_EN + _SEED_WORDS_ZH
        random.shuffle(all_seed_words)
        seed_hashes = [word_to_hash(w) for w in all_seed_words[:self._words_count * 2]]

        # 对每个种子词哈希找到最负责的节点
        seen_urls: set[str] = set()
        routed_targets: list[Seed] = []

        for wh in seed_hashes:
            responsible = _find_responsible_peers(
                word_hashes=[wh],
                peers=reachable,
                k=self._peers_count,
            )
            for _dist, peer in responsible:
                url = peer.base_url
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    routed_targets.append(peer)
                    if len(routed_targets) >= self._peers_count:
                        break
            if len(routed_targets) >= self._peers_count:
                break

        if not routed_targets:
            # 回退：最近未联系的节点
            reachable.sort(key=lambda s: s.last_contact)
            candidates = reachable[:self._peers_count * 2]
            random.shuffle(candidates)
            routed_targets = candidates[:self._peers_count]

        return routed_targets

    # ------------------------------------------------------------------
    # 定期 Pull
    # ------------------------------------------------------------------

    def start_periodic_pull(self, *, interval: int | None = None) -> None:
        """启动后台定期 Pull 线程。

        Args:
            interval: Pull 间隔（秒），None 使用默认值。
        """
        if self._pull_thread and self._pull_thread.is_alive():
            _logger.warning("定期 Pull 已在运行")
            return

        self._stop_event.clear()
        self._interval = interval or self._interval

        def _run() -> None:
            _logger.info("定期 Pull 已启动（间隔=%ds）", self._interval)
            while not self._stop_event.is_set():
                try:
                    self.pull_once()
                except Exception as exc:
                    _logger.error("定期 Pull 异常: %s", exc)

                # 等待下次 Pull（可被 stop_event 中断）
                self._stop_event.wait(timeout=self._interval)

            _logger.info("定期 Pull 已停止")

        self._pull_thread = threading.Thread(
            target=_run,
            name="pyacy-rwi-pull",
            daemon=True,
        )
        self._pull_thread.start()

    def stop_periodic_pull(self) -> None:
        """停止后台定期 Pull 线程。"""
        self._stop_event.set()
        if self._pull_thread:
            self._pull_thread.join(timeout=self._interval + 5)
            self._pull_thread = None

    @property
    def is_running(self) -> bool:
        """定期 Pull 是否正在运行。"""
        return (
            self._pull_thread is not None
            and self._pull_thread.is_alive()
        )

    # ------------------------------------------------------------------
    # 统计信息
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """获取 Pull 统计信息。

        Returns:
            包含 Pull 统计数据的字典。
        """
        return {
            "total_pulled": self._total_pulled,
            "total_pulls": self._total_pulls,
            "last_pull_time": self._last_pull_time,
            "is_running": self.is_running,
            "interval": self._interval,
            "storage_entries": self._storage.count(),
            "storage_unique_words": self._storage.unique_word_hashes(),
        }

    def __repr__(self) -> str:
        return (
            f"RWIPuller(pulled={self._total_pulled}, "
            f"pulls={self._total_pulls}, "
            f"running={self.is_running})"
        )
