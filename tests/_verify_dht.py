"""临时验证脚本：DHT 搜索 "ShanghaiTech University" 和 "上海科技大学"

此脚本仅用于本次验证，验证完成后删除。
"""
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format="[%(levelname)-5s] %(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, "src")
from pyacy import PYaCyNode

QUERIES = [
    "ShanghaiTech University",
    "上海科技大学",
    "university",  # 对照组：高频英文词
    "python",      # 对照组：常见技术词
]

def main():
    log.info("=" * 60)
    log.info("v0.3.0 DHT 搜索验证 — 哈希路由模式")
    log.info("=" * 60)

    # 创建节点并引导入网
    log.info("创建 PYaCyNode...")
    node = PYaCyNode(name="verify-search", port=8090)
    log.info(f"节点哈希：{node.hash}")

    log.info("开始 Bootstrap（简化模式，仅用 searchlab.eu）...")
    t0 = time.time()
    # 仅使用 searchlab.eu 这一个可靠的种子
    node.bootstrap(seed_urls=["http://yacy.searchlab.eu:8090"], max_peers=50, rounds=1)
    elapsed = time.time() - t0
    stats = node.get_peer_stats()
    log.info(f"Bootstrap 完成 ({elapsed:.1f}s): {stats['total_peers']} 节点，{stats.get('senior', 0)} Senior")

    if stats['total_peers'] == 0:
        log.error("Bootstrap 失败，无可用节点")
        node.close()
        return

    # 执行搜索
    for query in QUERIES:
        log.info("-" * 60)
        log.info(f"搜索：{query}")
        try:
            t0 = time.time()
            result = node.search(query, max_peers=10, iterative=False)
            elapsed = time.time() - t0

            references = result.references
            links = result.links
            peer_count = result.join_count
            ok = result.success

            log.info(f"  耗时：{elapsed:.1f}s")
            log.info(f"  成功：{ok}")
            log.info(f"  参与节点：{peer_count}")
            log.info(f"  引用数：{len(references)}")
            log.info(f"  链接数：{len(links)}")

            if references:
                log.info(f"  ✅ 搜索到结果！前 5 条：")
                for i, ref in enumerate(references[:5]):
                    title = ref.title or ref.url_hash[:12]
                    log.info(f"    [{i+1}] {title}")
            elif ok and len(references) == 0:
                log.info(f"  ⚠️  搜索成功但 RWI 无此词索引 (DHT 正常，网络覆盖不足)")

        except Exception as e:
            log.error(f"  ❌ 搜索失败：{e}")

    log.info("=" * 60)
    node.close()
    log.info("验证完成")

if __name__ == "__main__":
    main()
