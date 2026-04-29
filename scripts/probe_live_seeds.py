# -*- coding: utf-8 -*-
"""临时脚本：探测 YaCy 网络中的可达种子节点，生成硬编码种子列表。

运行方式::

    python scripts/probe_live_seeds.py

输出: 可达节点列表（JSON），用于更新 seeds.py 中的 HARDCODED_SEEDS。
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.error import URLError

# 添加项目根目录到 sys.path
sys.path.insert(0, "src")

from pyacy.p2p.seed import Seed, SeedKeys, PEERTYPE_SENIOR, PEERTYPE_PRINCIPAL

# 种子获取源
SEEDLIST_SOURCES = [
    "http://yacy.searchlab.eu:8090",
]

# 探测参数
PROBE_TIMEOUT = 8.0       # 每个请求超时（秒）
MAX_CONCURRENT = 30        # 最大并发数
MIN_UPTIME_HOURS = 24      # 最小在线时间（小时）
MIN_ICOUNT = 500           # 最小索引词数

# 输出文件
OUTPUT_FILE = "scripts/reachable_seeds.json"


def fetch_seedlist(source_url: str) -> list[dict]:
    """从种子源获取 seedlist.json。"""
    url = f"{source_url}/yacy/seedlist.json"
    try:
        req = Request(url, headers={"User-Agent": "PYaCy/0.2.5 seed-prober"})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # 处理两种格式：数组 和 {"peers": [...]}
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("peers", [])
            return []
    except Exception as e:
        print(f"[ERROR] 获取 seedlist 失败 ({source_url}): {e}")
        return []


def probe_seed(seed_data: dict) -> dict | None:
    """探测单个节点是否可达。"""
    # 构建 Seed 对象
    try:
        seed = Seed.from_json(seed_data)
    except Exception:
        return None

    # 只探测 Senior/Principal
    if not seed.is_senior():
        return None

    # 检查基本条件
    uptime_str = seed.get(SeedKeys.UPTIME, "0")
    try:
        uptime = int(uptime_str)
    except ValueError:
        uptime = 0

    if uptime < MIN_UPTIME_HOURS * 60:  # YaCy UPTIME 单位是分钟
        return None

    icount_str = seed.get(SeedKeys.ICOUNT, "0")
    try:
        icount = int(icount_str)
    except ValueError:
        icount = 0

    if icount < MIN_ICOUNT:
        return None

    # HTTP 可达性探测
    url = seed.base_url
    if not url:
        return None

    try:
        start = time.monotonic()
        req = Request(
            f"{url}/api/status_p.json",
            headers={"User-Agent": "PYaCy/0.2.5 seed-prober"},
        )
        with urlopen(req, timeout=PROBE_TIMEOUT) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                latency = time.monotonic() - start
                return {
                    "url": url,
                    "hash": seed.hash,
                    "name": seed.name,
                    "peertype": seed.get(SeedKeys.PEERTYPE),
                    "uptime_hours": round(uptime / 60, 1),
                    "icount": icount,
                    "latency": round(latency, 3),
                    "version": seed.get(SeedKeys.VERSION, ""),
                }
    except Exception:
        pass

    return None


def main():
    print("=" * 60)
    print("PYaCy 种子节点连通性探测")
    print("=" * 60)
    print(f"探测超时: {PROBE_TIMEOUT}s | 并发: {MAX_CONCURRENT}")
    print(f"条件: Senior/Principal, 在线≥{MIN_UPTIME_HOURS}h, 索引≥{MIN_ICOUNT}")
    print()

    # 1. 从种子源获取节点列表
    all_seeds: list[dict] = []
    for source in SEEDLIST_SOURCES:
        print(f"获取 seedlist: {source}")
        seeds = fetch_seedlist(source)
        print(f"  → {len(seeds)} 个节点")
        all_seeds.extend(seeds)

    if not all_seeds:
        print("[ERROR] 无法获取任何种子列表，退出。")
        sys.exit(1)

    # 去重（按 hash）
    seen = set()
    unique = []
    for s in all_seeds:
        h = s.get("Hash", s.get("hash", ""))
        if h and h not in seen:
            seen.add(h)
            unique.append(s)
    print(f"\n去重后: {len(unique)} 个唯一节点")

    # 2. 筛选 Senior/Principal
    senior_seeds = []
    for s in unique:
        try:
            seed = Seed.from_json(s)
            if seed.is_senior():
                senior_seeds.append(s)
        except Exception:
            pass
    print(f"Senior/Principal: {len(senior_seeds)} 个")

    # 3. 并行探测
    print(f"\n开始并行探测（{len(senior_seeds)} 个节点）...")
    start_time = time.monotonic()

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        futures = {executor.submit(probe_seed, s): s for s in senior_seeds}
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            if result:
                results.append(result)
                print(
                    f"  [{i:3d}/{len(senior_seeds)}] ✅ {result['name'][:30]:30s} "
                    f"{result['latency']:5.2f}s | {result['url']}"
                )

    elapsed = time.monotonic() - start_time

    # 按延迟排序
    results.sort(key=lambda r: r["latency"])

    # 4. 输出结果
    print(f"\n{'=' * 60}")
    print(f"探测完成: {len(results)}/{len(senior_seeds)} 个可达")
    print(f"耗时: {elapsed:.1f}s")
    print(f"{'=' * 60}")

    if results:
        print(f"\n可达种子节点 (前 30 个):")
        print(f"{'#':>3s}  {'延迟':>6s}  {'在线(h)':>8s}  {'索引':>8s}  {'名称':<30s}  URL")
        print("-" * 100)
        for i, r in enumerate(results[:30], 1):
            print(
                f"{i:3d}  {r['latency']:5.2f}s  {r['uptime_hours']:7.1f}h  "
                f"{r['icount']:7d}   {r['name'][:30]:30s}  {r['url']}"
            )

    # 保存到文件
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
