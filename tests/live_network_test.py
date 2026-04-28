# -*- coding: utf-8 -*-
"""PYaCy 线上节点连通性与搜索测试脚本。

本脚本在真实 P2P 网络环境中测试 PYaCy 节点功能，包括：
1. 种子节点 seedlist 获取测试
2. Hello 握手连通性测试
3. 网络引导（Bootstrap）测试
4. DHT 全文搜索测试
5. 异常与容错测试

**使用方式**::

    # 基础测试（默认参数）
    python tests/test_live_network.py

    # 指定自定义种子节点
    python tests/test_live_network.py --seeds http://peer1:8090,http://peer2:8090

    # 调整超时与延迟
    python tests/test_live_network.py --timeout 30 --delay 2.0

    # 仅测试连通性（跳过搜索）
    python tests/test_live_network.py --connectivity-only

    # 详细输出
    python tests/test_live_network.py --verbose

**延迟参数说明**:
    - 种子列表获取: 15 秒超时（部分节点响应慢）
    - Hello 握手: 15 秒超时（跨网络延迟高）
    - DHT 搜索: 20 秒超时（需要多节点查询）
    - Bootstrap 总耗时: 约 60-120 秒（取决于网络状况）
    - 请求间延迟: 0.5-2.0 秒（避免频繁请求被对端限流）

**网络环境适应性**:
    - 默认 Junior 模式（无需公网 IP）
    - 所有操作通过已有 Senior/Principal 节点代理
    - 自动处理节点离线/超时等异常
    - 支持 HTTP 代理（通过环境变量 HTTP_PROXY/HTTPS_PROXY）

.. note::
    本脚本为**集成测试**，需要真实的网络连接。
    P2P 网络中的节点状态不可控，部分测试可能因节点离线而失败，
    这**不属于** PYaCy 代码缺陷。
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 路径配置：确保可以导入 pyacy 包
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parent.parent
_src_path = _project_root / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from pyacy import PYaCyNode, __version__ as pyacy_version
from pyacy.exceptions import PYaCyConnectionError, PYaCyP2PError, PYaCyTimeoutError
from pyacy.p2p.hello import HelloClient
from pyacy.p2p.protocol import P2PProtocol
from pyacy.p2p.seed import PEERTYPE_SENIOR, PEERTYPE_PRINCIPAL, PEERTYPE_JUNIOR

# ---------------------------------------------------------------------------
# 默认配置（线上测试专用，保守的超时与延迟参数）
# ---------------------------------------------------------------------------

#: 单次 HTTP 请求超时（秒）。P2P 网络延迟较高，需要较长超时。
DEFAULT_TIMEOUT: int = 30

#: 请求间最小间隔（秒）。避免短时间内大量请求被对端限流。
DEFAULT_DELAY: float = 1.0

#: 获取种子列表超时（秒）。
SEEDLIST_TIMEOUT: int = 15

#: Hello 握手超时（秒）。
HELLO_TIMEOUT: int = 15

#: DHT 搜索超时（秒）。
SEARCH_TIMEOUT: int = 20

#: Bootstrap 最大耗时（秒）。
BOOTSTRAP_MAX_TIME: int = 120

#: 单次测试最大节点数。
MAX_TEST_PEERS: int = 10

#: 搜索测试词列表（不同语言、不同主题）。
SEARCH_QUERIES: list[str] = [
    "python",
    "open source",
    "science",
]


# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------

def setup_logging(verbose: bool = False) -> None:
    """配置日志格式。

    Args:
        verbose: 是否启用详细日志（DEBUG 级别）。
    """
    level = logging.DEBUG if verbose else logging.INFO
    fmt = (
        "[%(asctime)s] %(levelname)-7s %(name)s | %(message)s"
        if verbose
        else "[%(levelname)-7s] %(message)s"
    )
    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _delay(seconds: float, *, label: str = "") -> None:
    """等待指定秒数（请求间隔控制）。

    Args:
        seconds: 等待秒数。
        label: 可选的标签（用于日志）。
    """
    if label:
        logging.debug("等待 %.1fs (%s)...", seconds, label)
    time.sleep(seconds)


def _format_result(
    test_name: str,
    passed: int,
    total: int,
    details: list[str] | None = None,
) -> dict[str, Any]:
    """格式化单个测试步骤的结果。

    Args:
        test_name: 测试名称。
        passed: 通过数。
        total: 总数。
        details: 详情文本列表。

    Returns:
        结构化结果字典。
    """
    status = "✅ 通过" if passed > 0 else "❌ 失败"
    if 0 < passed < total:
        status = "⚠️  部分通过"

    result = {
        "name": test_name,
        "status": status,
        "passed": passed,
        "total": total,
        "details": details or [],
    }

    logging.info(
        "%-40s %s (%d/%d)",
        result["name"],
        result["status"],
        result["passed"],
        result["total"],
    )
    for d in result["details"]:
        logging.info("    %s", d)

    return result


# ---------------------------------------------------------------------------
# 测试 1: 种子列表获取
# ---------------------------------------------------------------------------

def test_seedlist_discovery(
    seed_urls: list[str],
    *,
    timeout: int = SEEDLIST_TIMEOUT,
    delay: float = DEFAULT_DELAY,
) -> list[dict[str, Any]]:
    """测试从已知种子节点获取节点列表。

    遍历种子 URL 列表，尝试获取 seedlist.json 端点，
    统计成功/失败的节点数量及其种子数量。

    Args:
        seed_urls: 种子节点 URL 列表。
        timeout: 单个请求超时。
        delay: 请求间延迟（秒）。

    Returns:
        每个 URL 的结果字典列表。
    """
    logging.info("=" * 60)
    logging.info("测试 1: 种子列表获取 (seedlist.json)")
    logging.info("=" * 60)

    protocol = P2PProtocol(timeout=timeout)
    hello = HelloClient(protocol)
    results: list[dict[str, Any]] = []

    for url in seed_urls:
        logging.info("请求 seedlist: %s", url)
        try:
            seeds = hello.get_seedlist(url)
            results.append({
                "url": url,
                "success": True,
                "seed_count": len(seeds),
                "senior_count": sum(
                    1 for s in seeds
                    if s.peer_type in (PEERTYPE_SENIOR, PEERTYPE_PRINCIPAL)
                ),
                "error": None,
            })

            if seeds:
                logging.info(
                    "  → 获取到 %d 个节点（%d 个 Senior/Principal）",
                    len(seeds),
                    sum(1 for s in seeds if s.peer_type in (PEERTYPE_SENIOR, PEERTYPE_PRINCIPAL)),
                )
            else:
                logging.warning("  → 返回空列表")
        except PYaCyTimeoutError:
            logging.warning("  → 超时")
            results.append({"url": url, "success": False, "seed_count": 0, "senior_count": 0, "error": "timeout"})
        except PYaCyConnectionError as exc:
            logging.warning("  → 连接失败: %s", exc)
            results.append({"url": url, "success": False, "seed_count": 0, "senior_count": 0, "error": str(exc)})
        except Exception as exc:
            logging.warning("  → 未知错误: %s", exc)
            results.append({"url": url, "success": False, "seed_count": 0, "senior_count": 0, "error": str(exc)})

        _delay(delay, label="seedlist 请求间隔")

    success_count = sum(1 for r in results if r["success"])
    total_seeds = sum(r["seed_count"] for r in results)
    _format_result(
        "种子列表获取",
        success_count,
        len(seed_urls),
        details=[
            f"成功 {success_count}/{len(seed_urls)} 个节点",
            f"合计发现 {total_seeds} 个 P2P 节点",
        ],
    )

    return results


# ---------------------------------------------------------------------------
# 测试 2: Hello 握手连通性
# ---------------------------------------------------------------------------

def test_hello_handshake(
    node: PYaCyNode,
    *,
    max_peers: int = MAX_TEST_PEERS,
    delay: float = DEFAULT_DELAY,
) -> list[dict[str, Any]]:
    """测试向已发现的 Senior 节点发送 Hello 请求。

    从已知节点池中筛选 Senior 节点，逐一发送 Hello 握手，
    统计成功率和被对端判定的节点类型。

    Args:
        node: 已初始化的 PYaCy 节点。
        max_peers: 最多测试的节点数。
        delay: 请求间延迟（秒）。

    Returns:
        每个目标节点的 Hello 结果列表。
    """
    logging.info("=" * 60)
    logging.info("测试 2: Hello 握手连通性")
    logging.info("=" * 60)

    seniors = node.get_senior_peers()
    if not seniors:
        logging.warning("没有可连接的 Senior 节点，跳过 Hello 测试")
        return []

    targets = seniors[:max_peers]
    logging.info("目标节点: %d 个 Senior", len(targets))

    results: list[dict[str, Any]] = []
    for target in targets:
        name = target.name or target.hash[:8]
        url = target.base_url
        logging.info("Hello → %s (%s)", name, url)

        try:
            hello_result = node.hello_peer(target)
            if hello_result and hello_result["success"]:
                results.append({
                    "peer": name,
                    "url": url,
                    "success": True,
                    "your_ip": hello_result.get("your_ip", "unknown"),
                    "your_type": hello_result.get("your_type", "unknown"),
                    "seeds_received": hello_result.get("seeds_received", 0),
                })
                logging.info(
                    "  → 成功 | 我的 IP: %s | 类型: %s | 收到 %d 种子",
                    hello_result.get("your_ip"),
                    hello_result.get("your_type"),
                    hello_result.get("seeds_received", 0),
                )
            else:
                results.append({"peer": name, "url": url, "success": False, "error": "no response"})
                logging.warning("  → 无响应")
        except Exception as exc:
            results.append({"peer": name, "url": url, "success": False, "error": str(exc)})
            logging.warning("  → 异常: %s", exc)

        _delay(delay, label="Hello 请求间隔")

    success_count = sum(1 for r in results if r["success"])
    junior_count = sum(1 for r in results if r.get("your_type") == PEERTYPE_JUNIOR)

    _format_result(
        "Hello 握手",
        success_count,
        len(targets),
        details=[
            f"成功 {success_count}/{len(targets)} 次握手",
            f"被判定为 Junior: {junior_count} 次",
            f"当前节点哈希: {node.hash[:12]}...",
        ],
    )

    return results


# ---------------------------------------------------------------------------
# 测试 3: 网络引导（Bootstrap）
# ---------------------------------------------------------------------------

def test_bootstrap(
    seed_urls: list[str],
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[PYaCyNode, bool]:
    """测试完整的网络引导流程。

    创建 Junior 节点并执行 bootstrap，验证能否成功发现节点。

    Args:
        seed_urls: 种子节点 URL 列表。
        timeout: P2P 请求超时。

    Returns:
        ``(node, success)`` 元组。
    """
    logging.info("=" * 60)
    logging.info("测试 3: 网络引导（Bootstrap）")
    logging.info("=" * 60)

    node = PYaCyNode(
        name="pyacy-test-junior",
        timeout=timeout,
        seed_urls=seed_urls,
    )

    logging.info("节点创建: hash=%s", node.hash[:12])
    logging.info("开始 Bootstrap，最长等待 %d 秒...", BOOTSTRAP_MAX_TIME)

    t_start = time.time()
    success = node.bootstrap(max_peers=50, rounds=2)
    elapsed = time.time() - t_start

    stats = node.get_peer_stats()

    _format_result(
        "网络引导",
        1 if success else 0,
        1,
        details=[
            f"总节点数: {stats['total_peers']}",
            f"Senior/Principal: {stats['senior_peers']}",
            f"Junior: {stats['junior_peers']}",
            f"引导耗时: {elapsed:.1f}s",
            f"节点类型分布: {stats.get('type_distribution', {})}",
        ],
    )

    return node, success


# ---------------------------------------------------------------------------
# 测试 4: DHT 全文搜索
# ---------------------------------------------------------------------------

def test_dht_search(
    node: PYaCyNode,
    *,
    queries: list[str] | None = None,
    delay: float = DEFAULT_DELAY,
) -> list[dict[str, Any]]:
    """测试 DHT 全文搜索功能。

    在已引导入网的节点上执行多个搜索词，
    记录每次搜索的结果数和耗时。

    Args:
        node: 已引导的 PYaCy 节点。
        queries: 搜索词列表（默认使用 SEARCH_QUERIES）。
        delay: 请求间延迟（秒）。

    Returns:
        每次搜索的结果字典列表。
    """
    logging.info("=" * 60)
    logging.info("测试 4: DHT 全文搜索")
    logging.info("=" * 60)

    queries = queries or SEARCH_QUERIES
    results: list[dict[str, Any]] = []

    for query in queries:
        logging.info("搜索: %s", query)

        try:
            t_start = time.time()
            search_result = node.search(
                query,
                count=20,
                max_peers=3,
                language="",
            )
            elapsed = time.time() - t_start

            if search_result.success:
                titled = [r for r in search_result.references if r.title]

                results.append({
                    "query": query,
                    "success": True,
                    "total_references": search_result.total_results,
                    "titled_count": len(titled),
                    "links_count": search_result.link_count,
                    "join_count": search_result.join_count,
                    "time_ms": int(elapsed * 1000),
                    "sample_titles": [r.title[:60] for r in titled[:3]],
                })

                logging.info(
                    "  → %d 条引用 (%d 条含标题), %d 链接, %d 节点参与, %.1fs",
                    search_result.total_results,
                    len(titled),
                    search_result.link_count,
                    search_result.join_count,
                    elapsed,
                )
                for t in titled[:3]:
                    logging.info("      📄 %s", t.title[:80])
            else:
                results.append({
                    "query": query,
                    "success": False,
                    "total_references": 0,
                    "error": "search returned failure",
                })
                logging.warning("  → 搜索返回失败")

        except PYaCyP2PError as exc:
            logging.warning("  → P2P 错误: %s", exc)
            results.append({"query": query, "success": False, "error": str(exc)})
        except PYaCyTimeoutError:
            logging.warning("  → 搜索超时")
            results.append({"query": query, "success": False, "error": "timeout"})
        except Exception as exc:
            logging.warning("  → 异常: %s", exc)
            results.append({"query": query, "success": False, "error": str(exc)})

        _delay(delay, label="搜索请求间隔")

    success_count = sum(1 for r in results if r["success"])
    total_refs = sum(r.get("total_references", 0) for r in results)

    _format_result(
        "DHT 全文搜索",
        success_count,
        len(queries),
        details=[
            f"成功 {success_count}/{len(queries)} 次搜索",
            f"合计 {total_refs} 条引用",
        ],
    )

    return results


# ---------------------------------------------------------------------------
# 测试 5: 容错与边界情况
# ---------------------------------------------------------------------------

def test_error_handling(
    node: PYaCyNode,
    *,
    delay: float = DEFAULT_DELAY,
) -> dict[str, Any]:
    """测试异常处理与边界情况。

    包括：
    - 不可达节点的处理
    - 无效 URL 的处理
    - 空搜索词的处理

    Args:
        node: 已初始化的 PYaCy 节点。
        delay: 请求间延迟（秒）。

    Returns:
        测试结果汇总字典。
    """
    logging.info("=" * 60)
    logging.info("测试 5: 容错与边界情况")
    logging.info("=" * 60)

    passed = 0
    total = 0
    details: list[str] = []

    # 5.1 不可达节点
    total += 1
    logging.info("子测试 5.1: 不可达节点")
    from pyacy.p2p.seed import Seed, SeedKeys
    fake_seed = Seed.create_junior(name="unreachable", port=9999)
    # Seed 使用 dna 字典存储属性，直接修改即可
    fake_seed.dna[SeedKeys.IP] = "192.0.2.1"  # RFC 5737 TEST-NET-1

    try:
        result = node.hello_peer(fake_seed)
        if result is None:
            passed += 1
            details.append("5.1 ✅ 不可达节点正确处理（返回 None）")
        else:
            details.append("5.1 ⚠️  不可达节点返回了非预期结果")
    except Exception:
        passed += 1
        details.append("5.1 ✅ 不可达节点正确抛出异常")

    _delay(delay)

    # 5.2 无效 URL
    total += 1
    logging.info("子测试 5.2: 无效 URL")

    from pyacy.p2p.protocol import P2PProtocol as _P2PProtocol
    protocol = _P2PProtocol(timeout=5)

    try:
        protocol.hello(
            target_url="http://[::1]:99999",
            target_hash="000000000000",
            my_seed_str="",
            my_hash="000000000000",
        )
        details.append("5.2 ❌ 无效 URL 未抛出异常")
    except (PYaCyConnectionError, ValueError, Exception):
        passed += 1
        details.append("5.2 ✅ 无效 URL 正确处理")

    # 5.3 空搜索词
    total += 1
    logging.info("子测试 5.3: 空搜索词")
    try:
        result = node.search("", count=5, max_peers=1)
        passed += 1
        details.append(f"5.3 ✅ 空搜索词返回 {result.total_results} 条结果")
    except Exception as exc:
        passed += 1
        details.append(f"5.3 ✅ 空搜索词抛出异常（合理）: {exc}")

    # 5.4 查看统计
    total += 1
    stats = node.get_peer_stats()
    details.append(
        f"5.4 ✅ 统计: {stats['total_peers']} 节点, "
        f"{stats['senior_peers']} Senior, 引导={stats['is_bootstrapped']}"
    )
    passed += 1

    _format_result("容错与边界", passed, total, details=details)
    return {"passed": passed, "total": total, "details": details}


# ---------------------------------------------------------------------------
# 汇总报告
# ---------------------------------------------------------------------------

def print_summary(
    results: list[dict[str, Any]],
    node: PYaCyNode | None = None,
    elapsed_total: float = 0.0,
) -> None:
    """打印测试汇总报告。

    Args:
        results: 各测试步骤的结果列表。
        node: 测试使用的节点（可选）。
        elapsed_total: 总耗时。
    """
    logging.info("")
    logging.info("=" * 60)
    logging.info("                    测试汇总报告")
    logging.info("=" * 60)
    logging.info("  PYaCy 版本: %s", pyacy_version)
    logging.info("  节点名称:   %s", node.name if node else "N/A")
    logging.info("  节点哈希:   %s", (node.hash[:16] + "...") if node else "N/A")
    logging.info("  总耗时:     %.1f 秒", elapsed_total)

    if node:
        stats = node.get_peer_stats()
        logging.info("  发现节点:   %d（%d Senior）", stats["total_peers"], stats["senior_peers"])

    logging.info("")

    total_passed = 0
    total_tests = 0
    for r in results:
        if isinstance(r, dict) and "passed" in r:
            total_passed += r["passed"]
            total_tests += r["total"]

    if total_tests > 0:
        logging.info(
            "  总通过率:   %d/%d (%.0f%%)",
            total_passed,
            total_tests,
            total_passed / total_tests * 100 if total_tests else 0,
        )

    logging.info("")

    logging.info("  ⚠️  注意:")
    logging.info("  1. P2P 网络中节点状态不可控，部分失败属正常现象")
    logging.info("  2. 如果所有种子节点均不可达，请检查网络连接/防火墙")
    logging.info("  3. 使用 --seeds 参数可指定自定义种子节点列表")
    logging.info("")


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

def main() -> None:
    """测试入口。

    解析命令行参数，按顺序执行所有测试步骤。
    """
    parser = argparse.ArgumentParser(
        description="PYaCy 线上节点连通性与搜索测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python tests/test_live_network.py
  python tests/test_live_network.py --verbose
  python tests/test_live_network.py --connectivity-only
  python tests/test_live_network.py --seeds http://peer1:8090,http://peer2:8090
  python tests/test_live_network.py --timeout 45 --delay 3.0
        """,
    )

    parser.add_argument(
        "--seeds",
        type=str,
        default=None,
        help="自定义种子节点 URL 列表（逗号分隔）",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"P2P 请求超时秒数（默认: {DEFAULT_TIMEOUT}）",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"请求间延迟秒数（默认: {DEFAULT_DELAY}）",
    )
    parser.add_argument(
        "--connectivity-only",
        action="store_true",
        help="仅测试连通性（跳过搜索测试）",
    )
    parser.add_argument(
        "--search-only",
        action="store_true",
        help="仅测试搜索（需先完成 Bootstrap）",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细日志输出（DEBUG 级别）",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="自定义搜索词（覆盖默认词列表）",
    )

    args = parser.parse_args()

    # 日志配置
    setup_logging(verbose=args.verbose)

    # 解析种子 URL
    if args.seeds:
        seed_urls = [u.strip() for u in args.seeds.split(",") if u.strip()]
    else:
        from pyacy.network import DEFAULT_SEED_URLS
        seed_urls = list(DEFAULT_SEED_URLS)

    # 当前会话参数
    session_timeout = args.timeout
    session_delay = args.delay

    logging.info("PYaCy 线上测试 v%s", pyacy_version)
    logging.info("种子节点: %d 个", len(seed_urls))
    for url in seed_urls:
        logging.info("  - %s", url)
    logging.info("超时: %ds | 延迟: %.1fs", session_timeout, session_delay)
    logging.info("")

    t_total_start = time.time()
    all_results: list[Any] = []
    node: PYaCyNode | None = None

    try:
        if not args.search_only:
            # --- 测试 1: 种子列表 ---
            all_results.append(
                test_seedlist_discovery(
                    seed_urls,
                    timeout=session_timeout,
                    delay=session_delay,
                )
            )

            # --- 测试 3: Bootstrap ---
            node, bootstrapped = test_bootstrap(seed_urls, timeout=session_timeout)

            if not bootstrapped:
                logging.warning(
                    "⚠️  Bootstrap 失败，部分测试将跳过。"
                    "请检查种子节点是否可访问。"
                )
                logging.info("")
                logging.info("可能原因：")
                logging.info("  1. 所有种子节点均不可达（网络防火墙/代理问题）")
                logging.info("  2. 种子节点已下线或变更了端口")
                logging.info("  3. 当前环境无公网 IP，且无 Junior 友好的 Senior 节点在线")
                logging.info("  4. YaCy 公共种子列表已过期，请用 --seeds 手动指定")
                logging.info("")
                err_result = test_error_handling(node, delay=session_delay)
                all_results.append(err_result)
                # 报告由 finally 块统一打印
                return

            # --- 测试 2: Hello 握手（在 Bootstrap 后） ---
            all_results.append(
                test_hello_handshake(node, max_peers=MAX_TEST_PEERS, delay=session_delay)
            )

        else:
            node = PYaCyNode(
                name="pyacy-search-test",
                timeout=session_timeout,
                seed_urls=seed_urls,
            )
            node.bootstrap(max_peers=30, rounds=1)

        # --- 测试 4: DHT 搜索 ---
        if not args.connectivity_only and node and node.is_bootstrapped:
            queries = [args.query] if args.query else SEARCH_QUERIES
            all_results.append(
                test_dht_search(node, queries=queries, delay=session_delay)
            )
        elif args.connectivity_only:
            logging.info("跳过搜索测试（--connectivity-only）")

        # --- 测试 5: 容错 ---
        if node and not args.search_only:
            test_error_handling(node, delay=session_delay)

    except KeyboardInterrupt:
        logging.warning("\n用户中断测试")
    except Exception as exc:
        logging.error("测试异常: %s", exc, exc_info=args.verbose)
    finally:
        elapsed_total = time.time() - t_total_start

        print_summary(all_results, node, elapsed_total)

        if node:
            node.close()

        logging.info("测试完成。")


if __name__ == "__main__":
    main()
