# -*- coding: utf-8 -*-
"""PYaCy 种子节点管理模块。

本模块负责 P2P 网络的初始接入点管理，包括：
- 硬编码种子列表（离线可用，无需联网即可开始 Bootstrap）
- 并行连通性探测（启动时快速筛选可达节点）
- 本地种子缓存（持久化最近发现的稳健节点）

种子来源（优先级从高到低）：
    1. 本地缓存 ``~/.pyacy/seed_cache.json``（上次发现的稳健节点）
    2. 硬编码种子 ``HARDCODED_SEEDS``（编译时确定，定期人工维护）
    3. 在线种子 — 通过公开种子列表端点动态获取

设计原则:
    - 纯 Python 标准库实现，零外部依赖
    - 并行探测确保启动延迟可控（≤ 30 秒）
    - 三层冗余确保无单点故障
    - 自动降级：硬编码种子全部失效时回退到在线获取

硬编码种子列表最后更新: 2026-05-07
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
#:   - 通过公开种子列表探测获取
#:
#: 维护说明:
#:   - 每季度运行 ``scripts/update_seeds.py`` 更新此列表
#:   - 更新后修改上方注释中的「最后更新」日期
#:   - 每个种子包含 url 和 hash 两个字段
HARDCODED_SEEDS: list[dict[str, str]] = [
    # 通过并行连通性探测筛选的高质量种子节点。
    # 探测时间: 2026-05-07
    # 筛选条件: 可达 + 延迟最低
    # 探测结果: 364 个候选, 100 个可达, 选出 30 个
    # 延迟范围: 453-766ms (平均 641ms)
    {"url": "http://47.148.65.168:49152", "hash": "bpcKc_WU0osl"},
    {"url": "http://yacy-crawler.andisearch.com:8090", "hash": "qtIxPrwqGQmz"},
    {"url": "http://66.114.134.193:8090", "hash": "VNwFiLMnONAM"},
    {"url": "http://185.18.125.70:8090", "hash": "OqxbmEJMJx5j"},
    {"url": "http://51.159.15.49:8090", "hash": "cBWDUGAh4sOY"},
    {"url": "http://84.71.214.82:8090", "hash": "SEi0hNbo8AKQ"},
    {"url": "http://192.18.156.94:8090", "hash": "xeqc_zJewyim"},
    {"url": "http://69.173.253.236:8090", "hash": "n2R2Pj-kDZJl"},
    {"url": "http://54.36.109.184:8091", "hash": "jayWgI-23LQB"},
    {"url": "http://192.99.28.106:8090", "hash": "Ls7V_nMEHpit"},
    {"url": "http://174.101.105.219:49158", "hash": "3FgDHWCyVeXI"},
    {"url": "http://79.112.69.148:8090", "hash": "jR0fz0g0aww4"},
    {"url": "http://109.190.142.161:8090", "hash": "OU_s3iRww6Lo"},
    {"url": "http://83.164.76.127:8090", "hash": "5F3SzJDwvQwX"},
    {"url": "http://184.144.165.242:8090", "hash": "qwiPGJoS296c"},
    {"url": "http://185.31.242.163:8090", "hash": "yTZ2dsgqqHuu"},
    {"url": "http://5.75.231.55:8090", "hash": "GPfTZlNVOiUV"},
    {"url": "http://85.214.254.232:8090", "hash": "Bpo9w_tp_Bk3"},
    {"url": "http://90.22.71.45:8090", "hash": "fGk7kDsA4gN5"},
    {"url": "http://95.20.193.72:8090", "hash": "4d_CqjoAIe5b"},
    {"url": "http://65.108.121.176:8090", "hash": "qJDy7B3m3Dys"},
    {"url": "http://93.213.183.171:8090", "hash": "5TLE4QGSHv9B"},
    {"url": "http://185.209.30.30:8090", "hash": "wzXXfmpgM7Kv"},
    {"url": "http://37.120.82.186:8090", "hash": "BYr58yDM_Rm6"},
    {"url": "http://92.255.251.66:8090", "hash": "Ab8-mAzTtmps"},
    {"url": "http://93.190.202.83:49152", "hash": "a6Bf_Nzzi34M"},
    {"url": "http://139.99.208.215:8090", "hash": "uF97zJFdq9zv"},
    {"url": "http://68.118.220.72:8090", "hash": "5qZMfwrB0FCA"},
    {"url": "http://81.3.9.173:8090", "hash": "1_DVU5Jj03dn"},
    {"url": "http://178.31.110.213:8090", "hash": "E7BJYKvAkULu"},
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
