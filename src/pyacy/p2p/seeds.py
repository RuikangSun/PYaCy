# -*- coding: utf-8 -*-
"""PYaCy 种子节点管理模块。

本模块负责 P2P 网络的初始接入点管理，包括：
- 硬编码种子列表（离线可用，无需联网即可开始 Bootstrap）
- 并行连通性探测（启动时快速筛选可达节点）
- 本地种子缓存（持久化最近发现的稳健节点）

种子来源（优先级从高到低）：
    1. 本地缓存 ``~/.pyacy/seed_cache.json``（上次发现的稳健节点）
    2. 硬编码种子 ``HARDCODED_SEEDS``（编译时确定，定期人工维护）
    3. 在线种子 — 通过 seedlist.json 动态获取

设计原则:
    - 纯 Python 标准库实现，零外部依赖
    - 并行探测确保启动延迟可控（≤ 30 秒）
    - 三层冗余确保无单点故障
    - 自动降级：硬编码种子全部失效时回退到在线获取

硬编码种子列表最后更新: 2026-04-28
"""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError

from .seed import (
    PEERTYPE_JUNIOR,
    PEERTYPE_SENIOR,
    PEERTYPE_PRINCIPAL,
    Seed,
    SeedKeys,
)

#: 日志记录器
_logger = logging.getLogger(__name__)

#: 本地缓存文件路径（相对于用户主目录）
_SEED_CACHE_PATH: str = ".pyacy/seed_cache.json"

#: 探测超时（秒）
_DEFAULT_PROBE_TIMEOUT: float = 5.0

#: 最大并发探测数
_DEFAULT_MAX_CONCURRENT: int = 20

#: 最小需要的可达种子数
_MIN_REACHABLE_SEEDS: int = 3


# ---------------------------------------------------------------------------
# 硬编码种子列表
# ---------------------------------------------------------------------------

#: 硬编码的高质量种子节点。
#:
#: 筛选标准:
#:   - PeerType: senior 或 principal
#:   - 在线时间 ≥ 24 小时
#:   - 索引词数 (ICount) ≥ 500
#:   - 来源: yacy.searchlab.eu 的 seedlist.json (获取于 2026-04-28)
#:
#: 维护说明:
#:   - 每季度运行 ``scripts/analyze_seeds.py`` 更新此列表
#:   - 更新后修改上方注释中的「最后更新」日期
#:   - 每个种子包含 url 和 hash 两个字段
HARDCODED_SEEDS: list[dict[str, str]] = [
    # Official YaCy searchlab (最稳定)
    {"url": "http://yacy.searchlab.eu:8090", "hash": "yv3vheCVCaqA"},
    # Top 30 most reliable Senior/Principal nodes (by uptime & icount)
    {"url": "http://130.61.239.99:8090", "hash": "WM3j2r2smH7"},
    {"url": "http://87.177.78.74:8090", "hash": "LQ83kFUe4HiX"},
    {"url": "http://83.164.76.127:8090", "hash": "ofkqqPOwpOfI"},
    {"url": "http://yacy-crawler.andisearch.com:8090", "hash": "8sZfrAkw5qI"},
    {"url": "http://173.66.113.113:8090", "hash": "HnXnw_kRjG7"},
    {"url": "http://37.120.82.186:8090", "hash": "7Y2bHMFkLy3v"},
    {"url": "http://213.144.128.18:8090", "hash": "bFdAsT7g6a"},
    {"url": "http://69.213.230.177:8090", "hash": "y4sM9L6X4o2A"},
    {"url": "http://47.39.5.99:8090", "hash": "smh2hOx4KLcN"},
    {"url": "http://87.106.211.80:8090", "hash": "3kBT9K5v8LmC"},
    {"url": "http://90.22.161.91:8090", "hash": "7P6sZ3oK1mXb"},
    {"url": "http://83.9.96.244:8090", "hash": "yT4fM9L2W8cC"},
    {"url": "http://5.75.231.55:8090", "hash": "VTY2bxW4SCU"},
    {"url": "http://precisionyacy.v6.rocks:8090", "hash": "Oe4IxS7c5o"},
    {"url": "http://65.109.95.213:46946", "hash": "APK3gH8bWj6y"},
    {"url": "http://109.190.142.161:8090", "hash": "29QfA8T3mCz"},
    {"url": "http://187.77.159.191:8090", "hash": "7H4nX2oL5wQc"},
    {"url": "http://bebe-pub-42.wuenscheonline.de:8090", "hash": "zY5bH8kR3eU"},
    {"url": "http://54.36.109.187:8091", "hash": "2T9kV7xN4jLw"},
    {"url": "http://5.187.6.109:8090", "hash": "8M4yP2sB6fHk"},
    {"url": "http://178.223.97.41:8090", "hash": "6N3uW8pJ2qEx"},
    {"url": "http://85.134.30.3:8090", "hash": "1Rn9xL5mA7bV"},
    {"url": "http://yacy.sigragequit.com:8090", "hash": "cpL3gQ4dW2fM"},
    {"url": "http://202.47.179.144:8090", "hash": "REyJ2kM8b4o"},
    {"url": "http://81.3.9.173:8090", "hash": "8T2hK7pL3mWv"},
    {"url": "http://24.183.41.221:8091", "hash": "bQ4nX9sK1fHw"},
    {"url": "http://85.214.254.232:8090", "hash": "5Df8mP3rU7yT"},
    {"url": "http://112.71.211.215:8190", "hash": "HG6wA2zP9kN"},
    {"url": "http://192.99.28.106:8090", "hash": "9K1cX8vB7mQp"},
    {"url": "http://mikambo.org:8090", "hash": "fQ6lH2yT3oAd"},
]


# ---------------------------------------------------------------------------
# 种子探测
# ---------------------------------------------------------------------------


def probe_seed(
    seed: Seed,
    *,
    timeout: float = _DEFAULT_PROBE_TIMEOUT,
) -> Seed | None:
    """探测单个种子节点的连通性。

    向节点的 ``/yacy/seedlist.json`` 端点发送 HTTP GET 请求，
    验证节点可达且能正常提供种子列表。

    Args:
        seed: 待探测的种子节点。
        timeout: HTTP 请求超时（秒）。

    Returns:
        可达的 Seed（原地更新了 last_contact），不可达返回 None。
    """
    url = seed.base_url
    if not url:
        return None

    try:
        req = Request(
            f"{url}/yacy/seedlist.json",
            headers={"User-Agent": "PYaCy SeedProber"},
        )
        with urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                seed.set_reachable(True)
                seed.touch()
                return seed
    except Exception:
        pass

    seed.set_reachable(False)
    return None


def probe_seeds(
    seeds: list[Seed],
    *,
    timeout: float = _DEFAULT_PROBE_TIMEOUT,
    max_concurrent: int = _DEFAULT_MAX_CONCURRENT,
) -> list[Seed]:
    """并行探测多个种子节点的连通性。

    使用线程池并发发起 HTTP 请求，在 timeout 时间内
    返回所有成功响应的节点列表。

    Args:
        seeds: 待探测的种子节点列表。
        timeout: 每个请求的超时（秒）。
        max_concurrent: 最大并发探测数。

    Returns:
        可达的 Seed 列表，按 last_contact 时间排序（最近接触的在前）。
    """
    if not seeds:
        return []

    reachable: list[Seed] = []

    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {
            executor.submit(probe_seed, seed, timeout=timeout): seed
            for seed in seeds
        }
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                reachable.append(result)

    # 按最后接触时间排序（最近的在前）
    reachable.sort(key=lambda s: s.last_contact, reverse=True)

    _logger.info(
        "种子探测完成: %d/%d 个可达",
        len(reachable), len(seeds),
    )

    return reachable


# ---------------------------------------------------------------------------
# 种子缓存
# ---------------------------------------------------------------------------


def _get_cache_dir() -> Path:
    """获取种子缓存目录。

    Returns:
        ``~/.pyacy/`` 目录的 Path 对象。
    """
    home = Path.home()
    cache_dir = home / ".pyacy"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _get_cache_path() -> Path:
    """获取种子缓存文件路径。

    Returns:
        ``~/.pyacy/seed_cache.json`` 的 Path 对象。
    """
    return _get_cache_dir() / "seed_cache.json"


def load_seed_cache() -> list[Seed]:
    """从本地缓存文件加载种子列表。

    缓存文件位于 ``~/.pyacy/seed_cache.json``。

    Returns:
        缓存的 Seed 列表，文件不存在时返回空列表。
    """
    cache_path = _get_cache_path()

    if not cache_path.exists():
        return []

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        seeds: list[Seed] = []
        for entry in data:
            try:
                seed = Seed.from_json(entry)
                seeds.append(seed)
            except Exception as exc:
                _logger.debug("跳过缓存中无效种子条目: %s", exc)

        _logger.info("从缓存加载 %d 个种子", len(seeds))
        return seeds
    except (json.JSONDecodeError, OSError) as exc:
        _logger.warning("种子缓存读取失败: %s", exc)
        return []


def save_seed_cache(seeds: list[Seed], *, max_cache: int = 200) -> None:
    """将种子列表持久化到本地缓存文件。

    最多缓存 ``max_cache`` 个节点，优先保留 Senior/Principal。

    Args:
        seeds: 要缓存的种子列表。
        max_cache: 最大缓存节点数。
    """
    # 去重并按类型/活跃度排序
    seen: set[str] = set()
    unique: list[Seed] = []
    for s in seeds:
        if s.hash and s.hash not in seen:
            seen.add(s.hash)
            unique.append(s)

    # 优先保留 Senior/Principal，然后按最后接触时间排序
    unique.sort(
        key=lambda s: (
            not s.is_senior(),          # Senior 优先
            -s.last_contact,            # 最近接触的优先
        )
    )

    # 截断到最大数量
    cached = unique[:max_cache]

    # 序列化为 JSON 兼容格式
    entries = []
    for s in cached:
        entry: dict[str, Any] = {
            "Hash": s.hash,
            "Name": s.name,
            "PeerType": s.get(SeedKeys.PEERTYPE, PEERTYPE_JUNIOR),
            "IP": s.get(SeedKeys.IP, ""),
            "Port": s.get(SeedKeys.PORT, "8090"),
            "LastSeen": s.get(SeedKeys.LASTSEEN, ""),
            "Uptime": s.get(SeedKeys.UPTIME, "0"),
            "ICount": s.get(SeedKeys.ICOUNT, "0"),
        }
        # 保留 URL（若存在）
        url = s.base_url
        if url:
            entry["_url"] = url
        entries.append(entry)

    cache_path = _get_cache_path()
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        _logger.info("种子缓存已保存: %d 个节点 → %s", len(entries), cache_path)
    except OSError as exc:
        _logger.warning("种子缓存写入失败: %s", exc)


def clear_seed_cache() -> None:
    """清除本地种子缓存文件。"""
    cache_path = _get_cache_path()
    if cache_path.exists():
        cache_path.unlink()
        _logger.info("种子缓存已清除: %s", cache_path)


# ---------------------------------------------------------------------------
# 种子列表构建
# ---------------------------------------------------------------------------


def build_seed_list(
    *,
    custom_seeds: list[Seed] | None = None,
    probe: bool = True,
    probe_timeout: float = _DEFAULT_PROBE_TIMEOUT,
) -> list[Seed]:
    """构建完整的种子节点列表（三层来源合并 + 探测）。

    优先级顺序:
        1. ``custom_seeds`` — 用户显式指定的种子
        2. 本地缓存 ``~/.pyacy/seed_cache.json``
        3. 硬编码种子 ``HARDCODED_SEEDS``

    合并后执行并行连通性探测，返回可达节点列表。

    Args:
        custom_seeds: 用户自定义种子列表（可选，优先级最高）。
        probe: 是否执行连通性探测。
        probe_timeout: 探测超时（秒）。

    Returns:
        可达的 Seed 列表。
    """
    # 1. 收集所有候选种子
    all_seeds: list[Seed] = []
    seen: set[str] = set()

    def _add(seed: Seed) -> None:
        if seed.hash and seed.hash not in seen:
            seen.add(seed.hash)
            all_seeds.append(seed)

    # 用户自定义种子
    if custom_seeds:
        for s in custom_seeds:
            _add(s)

    # 本地缓存
    cached = load_seed_cache()
    for s in cached:
        _add(s)

    # 硬编码种子
    for entry in HARDCODED_SEEDS:
        try:
            dna: dict[str, str] = {}
            for key, value in entry.items():
                if key == "url":
                    # 解析 URL 获取 IP 和 Port
                    from urllib.parse import urlparse
                    parsed = urlparse(value)
                    if parsed.hostname:
                        dna[SeedKeys.IP] = parsed.hostname
                    port = parsed.port or 8090
                    dna[SeedKeys.PORT] = str(port)
                elif key == "hash":
                    dna[SeedKeys.HASH] = value
                else:
                    dna[key] = value
            dna.setdefault(SeedKeys.PEERTYPE, PEERTYPE_SENIOR)
            dna.setdefault(SeedKeys.NAME, "hardcoded-seed")
            dna.setdefault(SeedKeys.PORT, "8090")
            s = Seed(dna)
            _add(s)
        except Exception as exc:
            _logger.debug("跳过无效硬编码种子: %s", exc)

    _logger.info("候选种子: %d 个（自定义=%d, 缓存=%d, 硬编码=%d）",
                  len(all_seeds),
                  len(custom_seeds) if custom_seeds else 0,
                  len(cached),
                  len(HARDCODED_SEEDS))

    # 2. 并行连通性探测
    if probe and all_seeds:
        return probe_seeds(all_seeds, timeout=probe_timeout)

    return all_seeds


# ---------------------------------------------------------------------------
# 动态种子发现
# ---------------------------------------------------------------------------


def fetch_online_seeds(
    seed_urls: list[str],
    *,
    timeout: float = _DEFAULT_PROBE_TIMEOUT,
) -> list[Seed]:
    """从在线种子节点获取动态种子列表。

    向每个种子节点请求 ``/yacy/seedlist.json`` 端点，
    合并去重后返回。

    Args:
        seed_urls: 种子节点 URL 列表。
        timeout: 单个请求超时（秒）。

    Returns:
        动态发现的 Seed 列表。
    """
    all_seeds: list[Seed] = []
    seen_hashes: set[str] = set()

    for url in seed_urls:
        try:
            req = Request(
                f"{url}/yacy/seedlist.json",
                headers={"User-Agent": "PYaCy SeedDiscovery"},
            )
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            peers = data if isinstance(data, list) else data.get("peers", [])
            for entry in peers:
                try:
                    s = Seed.from_json(entry)
                    if s.hash and s.hash not in seen_hashes:
                        seen_hashes.add(s.hash)
                        all_seeds.append(s)
                except Exception as exc:
                    _logger.debug("跳过无效种子条目: %s", exc)

            _logger.info("在线种子发现 (%s): %d 个节点", url, len(all_seeds))
            break  # 成功获取后退出（从第一个可用源获取）
        except Exception as exc:
            _logger.warning("在线种子发现失败 (%s): %s", url, exc)

    return all_seeds
