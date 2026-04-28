# -*- coding: utf-8 -*-
"""PYaCy Hello 协议交互模块。

本模块封装了 YaCy P2P 的 Hello 协议交互，包括：
- 向远程节点发送 Hello 请求
- 解析 Hello 响应（获取节点类型判定、种子列表）
- 基于 Hello 的节点发现

Hello 协议是 YaCy P2P 网络的核心握手协议。通过 Hello 请求，
节点可以：
1. 宣告自己的存在并提交种子信息
2. 获得对方对自己的类型判定（Junior/Senior/Principal）
3. 发现网络中的其他节点（种子列表）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .protocol import P2PProtocol, P2PResponse
from .seed import (
    PEERTYPE_JUNIOR,
    PEERTYPE_SENIOR,
    PEERTYPE_PRINCIPAL,
    PEERTYPE_VIRGIN,
    Seed,
    SeedKeys,
)

#: 日志记录器
_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hello 响应数据模型
# ---------------------------------------------------------------------------


@dataclass
class HelloResult:
    """Hello 协议响应的解析结果。

    Attributes:
        success: Hello 是否成功。
        message: 响应消息。
        your_ip: 对方看到的我们的 IP。
        your_type: 对方判定的节点类型（junior/senior/principal）。
        seeds: 从响应中提取的种子列表。
        raw: 原始响应字典。
    """

    success: bool = False
    message: str = ""
    your_ip: str = ""
    your_type: str = PEERTYPE_JUNIOR
    seeds: list[Seed] = field(default_factory=list)
    raw: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_response(cls, response: P2PResponse) -> "HelloResult":
        """从 P2P 响应解析 Hello 结果。

        Args:
            response: P2P 协议响应。

        Returns:
            HelloResult 实例。
        """
        data = response.data
        message = data.get("message", data.get("__status__", ""))

        # 检查是否成功: message 以 "ok" 开头，或 __status__ 以 "ok" 开头
        # YaCy Hello 响应有两种格式：
        #   - message=ok 263     (标准 key=value 格式)
        #   - ok 263             (纯状态行，无 "=" 号)
        raw_first_line = response.raw.strip().split("\n")[0].strip() if response.raw else ""
        success = (
            message.startswith("ok")
            or raw_first_line.startswith("ok")
        )

        # 提取 our type
        your_type = data.get(SeedKeys.YOURTYPE, PEERTYPE_JUNIOR)
        if your_type not in ("junior", "senior", "principal", "virgin", "mentee", "mentor"):
            your_type = PEERTYPE_JUNIOR

        # 提取 our IP
        your_ip = data.get("yourip", "")

        # 提取种子列表
        seeds: list[Seed] = []
        seedlist_str = data.get("seedlist", "")
        if seedlist_str:
            seeds = _parse_seedlist(seedlist_str)

        return cls(
            success=success,
            message=message,
            your_ip=your_ip,
            your_type=your_type,
            seeds=seeds,
            raw=data,
        )

    @property
    def is_junior(self) -> bool:
        """是否被判定为 Junior 节点。"""
        return self.your_type == PEERTYPE_JUNIOR

    @property
    def is_senior(self) -> bool:
        """是否被判定为 Senior/Principal 节点。"""
        return self.your_type in (PEERTYPE_SENIOR, PEERTYPE_PRINCIPAL)


# ---------------------------------------------------------------------------
# Hello 客户端
# ---------------------------------------------------------------------------


class HelloClient:
    """YaCy Hello 协议客户端。

    封装了 Hello 请求的完整生命周期，包括：
    - 发送 Hello 请求
    - 解析响应以获取节点类型和种子列表
    - 批量发现节点

    使用示例::

        client = HelloClient(protocol)
        result = client.hello_peer(
            target_url="http://peer:8090",
            target_hash="abc123...",
            my_seed=local_seed,
        )
        print(f"I am {result.your_type} (IP: {result.your_ip})")
        print(f"Discovered {len(result.seeds)} peers")
    """

    def __init__(self, protocol: P2PProtocol):
        """初始化 Hello 客户端。

        Args:
            protocol: P2P 协议实例。
        """
        self.protocol: P2PProtocol = protocol

    # ------------------------------------------------------------------
    # Hello 单节点
    # ------------------------------------------------------------------

    def hello_peer(
        self,
        target_url: str,
        target_hash: str,
        my_seed: Seed,
        *,
        count: int = 20,
        magic: int = 0,
    ) -> HelloResult:
        """向单个远程节点发送 Hello 请求。

        Args:
            target_url: 目标节点 URL。
            target_hash: 目标节点哈希。
            my_seed: 本地节点 Seed。
            count: 期望返回的种子数量（默认 20）。
            magic: 网络魔数（0 表示 freeworld）。

        Returns:
            HelloResult 实例。
        """
        my_seed_str = my_seed.to_seed_string()

        try:
            response = self.protocol.hello(
                target_url=target_url,
                target_hash=target_hash,
                my_seed_str=my_seed_str,
                my_hash=my_seed.hash,
                count=count,
                magic=magic,
            )
            return HelloResult.from_response(response)
        except Exception as exc:
            _logger.warning("Hello to %s failed: %s", target_url, exc)
            return HelloResult(
                success=False,
                message=str(exc),
            )

    # ------------------------------------------------------------------
    # 多节点 Hello（并发发现）
    # ------------------------------------------------------------------

    def hello_multiple(
        self,
        targets: list[tuple[str, str]],
        my_seed: Seed,
        *,
        count: int = 10,
        max_workers: int = 5,
    ) -> list[HelloResult]:
        """向多个节点并发发送 Hello 请求。

        使用线程池并发执行，加速节点发现。

        Args:
            targets: 目标节点列表，每项为 ``(url, hash)``。
            my_seed: 本地节点 Seed。
            count: 每个请求期望返回的种子数。
            max_workers: 最大并发数。

        Returns:
            HelloResult 列表（顺序与 targets 一致）。
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: list[HelloResult | None] = [None] * len(targets)

        def _hello_one(idx: int, url: str, hsh: str) -> tuple[int, HelloResult]:
            result = self.hello_peer(
                target_url=url,
                target_hash=hsh,
                my_seed=my_seed,
                count=count,
            )
            return idx, result

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_hello_one, i, url, hsh): i
                for i, (url, hsh) in enumerate(targets)
            }
            for future in as_completed(futures):
                try:
                    idx, result = future.result()
                    results[idx] = result
                except Exception as exc:
                    idx = futures[future]
                    _logger.warning("Hello to target %d failed: %s", idx, exc)
                    results[idx] = HelloResult(success=False, message=str(exc))

        return [r for r in results if r is not None]

    # ------------------------------------------------------------------
    # 种子列表获取
    # ------------------------------------------------------------------

    def get_seedlist(self, target_url: str) -> list[Seed]:
        """从远程节点获取种子列表（Bootstrap）。

        使用 /yacy/seedlist.json 端点获取已知节点列表。
        支持两种响应格式：
        - ``{"peers": [{...}, ...]}``（标准 JSON 格式）
        - ``[{...}, ...]``（扁平数组格式，旧版）

        Args:
            target_url: 目标节点 URL。

        Returns:
            解析后的 Seed 列表。
        """
        try:
            data = self.protocol.seedlist(target_url)
        except Exception as exc:
            _logger.warning("获取 seedlist 失败: %s", exc)
            return []

        # seedlist.json 标准格式: {"peers": [{...}, ...]}
        if isinstance(data, dict) and "peers" in data:
            peer_list = data["peers"]
            if isinstance(peer_list, list):
                seeds: list[Seed] = []
                for item in peer_list:
                    try:
                        seed = Seed.from_json(item)
                        seeds.append(seed)
                    except Exception as exc:
                        _logger.debug("解析种子条目失败: %s", exc)
                _logger.debug("seedlist.json: 解析 %d/%d 个节点", len(seeds), len(peer_list))
                return seeds

        # 扁平数组格式: [{...}, ...]
        if isinstance(data, list):
            seeds: list[Seed] = []
            for item in data:
                try:
                    seed = Seed.from_json(item)
                    seeds.append(seed)
                except Exception as exc:
                    _logger.debug("解析种子条目失败: %s", exc)
            return seeds

        # HTML 格式的 seedlist（回退）
        if isinstance(data, P2PResponse):
            seedlist_str = data.get("seedlist", "")
            if seedlist_str:
                return _parse_seedlist(seedlist_str)

        return []

    # ------------------------------------------------------------------
    # 发现种子网络
    # ------------------------------------------------------------------

    def discover_network(
        self,
        seed_urls: list[str],
        my_seed: Seed,
        *,
        max_peers: int = 100,
        rounds: int = 2,
    ) -> list[Seed]:
        """从入口节点开始逐轮发现 P2P 网络。

        第一轮：从所有种子 URL 获取种子列表并 Hello 连通
        第二轮：从已发现节点继续扩展

        Args:
            seed_urls: 入口节点的 URL 列表。
            my_seed: 本地节点 Seed。
            max_peers: 最大发现节点数。
            rounds: 发现轮数（默认 2）。

        Returns:
            发现的所有节点列表（去重）。
        """
        known_seeds: dict[str, Seed] = {}  # hash → Seed

        # 第一轮：从入口节点获取种子列表
        _logger.info("开始节点发现（第 1 轮），入口节点: %d 个", len(seed_urls))
        for url in seed_urls:
            seeds = self.get_seedlist(url)
            for seed in seeds:
                if seed.hash not in known_seeds:
                    known_seeds[seed.hash] = seed

        _logger.info("第 1 轮发现 %d 个节点", len(known_seeds))

        # 后续轮：从已发现的 Senior 节点继续扩展
        for round_num in range(2, rounds + 1):
            if len(known_seeds) >= max_peers:
                break

            # 选取可连接的 Senior 节点
            reachable = [
                s for s in known_seeds.values()
                if s.is_reachable and s.is_senior()
            ]
            if not reachable:
                _logger.info("无可连接的 Senior 节点，停止发现")
                break

            # 限制每轮的 hello 数量
            targets_this_round = reachable[:10]
            targets = [
                (s.base_url, s.hash)
                for s in targets_this_round
                if s.base_url
            ]

            if not targets:
                break

            _logger.info("开始节点发现（第 %d 轮），目标: %d 个节点", round_num, len(targets))
            results = self.hello_multiple(targets, my_seed, count=20)

            new_count = 0
            for result in results:
                for seed in result.seeds:
                    if seed.hash not in known_seeds:
                        known_seeds[seed.hash] = seed
                        new_count += 1

            _logger.info("第 %d 轮发现 %d 个新节点", round_num, new_count)

            if new_count == 0:
                break

        result = list(known_seeds.values())
        _logger.info("节点发现完成，共 %d 个节点", len(result))
        return result


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _parse_seedlist(seedlist_str: str) -> list[Seed]:
    """解析种子列表字符串。

    seedlist 格式::

        seed0=<seed_str>
        seed1=<seed_str>
        ...

    Args:
        seedlist_str: 种子列表字符串。

    Returns:
        解析后的 Seed 列表。
    """
    seeds: list[Seed] = []
    for line in seedlist_str.splitlines():
        line = line.strip()
        if not line:
            continue
        eq_pos = line.find("=")
        if eq_pos > 0:
            seed_str = line[eq_pos + 1:]
            try:
                seed = Seed.from_seed_string(seed_str)
                seeds.append(seed)
            except Exception as exc:
                _logger.debug("解析种子失败: %s (seed=%.50s...)", exc, seed_str)
    return seeds
