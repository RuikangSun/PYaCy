# -*- coding: utf-8 -*-
"""PYaCy综合使用示例。

展示所有核心功能：
  1. HTTP 客户端 — 连接已运行的 YaCy 节点
  2. P2P 节点 — 直接接入 YaCy 分布式网络
  3. 高级搜索语法 — site:/filetype:/intitle: 等操作符
  4. 爬虫 + 本地索引 — 网页抓取与 SQLite FTS5 全文索引
  5. RWI Pull — 无需公网 IP 积累本地索引
  6. API 适配器 — 统一搜索接口

运行要求：
  - Python ≥ 3.9
  - pip install -e .（零运行时依赖）
  - 模式 2/3/4/5 需要网络连接和可达的 YaCy 种子节点
"""

import sys
from pathlib import Path

# 确保可以导入 pyacy（当直接运行此脚本时）
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# =============================================================================
# 模式 1: HTTP 客户端 — 连接已运行的 YaCy 节点
# =============================================================================
def demo_http_client():
    """演示 HTTP 客户端模式：连接远程 YaCy 节点的 REST API。"""
    from pyacy import YaCyClient

    print("=" * 60)
    print("模式 1: HTTP 客户端")
    print("=" * 60)

    # 使用 YaCy 公共搜索节点
    with YaCyClient("http://yacy.searchlab.eu:8090") as client:
        # 检查连接
        if not client.ping():
            print("❌ 无法连接到 yacy.searchlab.eu:8090")
            return

        print("✅ 已连接")

        # 搜索
        print("\n--- 搜索 'ShanghaiTech University' ---")
        results = client.search("ShanghaiTech University", resource="global", maximum_records=5)
        for i, item in enumerate(results.items[:3], 1):
            print(f"  {i}. {item.title[:70]}")
            print(f"     {item.link}")

        # 节点状态
        status = client.status()
        print(f"\n--- 节点状态 ---")
        print(f"  名称: {status.name}")
        print(f"  索引: {status.index_size} 文档")
        if hasattr(status, 'uptime_hours'):
            print(f"  运行时间: {status.uptime_hours:.1f}h")


# =============================================================================
# 模式 2: P2P 节点 — 直接接入 YaCy 分布式网络
# =============================================================================
def demo_p2p_node():
    """演示 P2P 节点模式：创建节点并引导入网，执行 DHT 分布式搜索。"""
    from pyacy import PYaCyNode

    print("\n" + "=" * 60)
    print("模式 2: P2P 节点")
    print("=" * 60)

    node = PYaCyNode(name="pyacy-demo")
    print(f"节点创建: {node.name} (hash={node.hash[:12]}...)")

    # 引导入网
    print("正在引导入网...（约 30-60 秒）")
    bootstrapped = node.bootstrap(timeout=120)
    if not bootstrapped:
        print("⚠️  引导失败（可能无可用种子节点），跳过后续演示")
        node.close()
        return

    stats = node.get_peer_stats()
    print(f"引导成功！发现 {stats['total_peers']} 个节点，{stats.get('senior_peers', 0)} 个 Senior")

    # DHT 分布式搜索
    print("\n--- DHT 搜索 'python' ---")
    results = node.search("python", count=5)
    for i, ref in enumerate(results.references[:3], 1):
        print(f"  {i}. {ref.title[:70]}")
        print(f"     {ref.url}")

    node.close()


# =============================================================================
# 模式 3: 高级搜索语法
# =============================================================================
def demo_advanced_search():
    """演示 v0.4.1 高级搜索语法：site:/filetype:/intitle: 等操作符。"""
    from pyacy.search import SearchQuery

    print("\n" + "=" * 60)
    print("模式 3: 高级搜索语法")
    print("=" * 60)

    # 解析高级搜索
    queries = [
        'site:github.com python async',
        'filetype:pdf machine learning',
        'site:edu intitle:"deep learning"',
        '/language/en artificial intelligence',
        'python -java -perl',
    ]

    for qs in queries:
        q = SearchQuery(qs)
        print(f"\n  查询: '{qs}'")
        print(f"  → 纯文本: '{q.effective_query}'")
        if q.site:
            print(f"  → site: '{q.site}'")
        if q.filetype:
            print(f"  → filetype: '{q.filetype}'")
        if q.intitle:
            print(f"  → intitle: {q.intitle}")
        if q.language:
            print(f"  → language: '{q.language}'")
        if q.exclude_words:
            print(f"  → 排除词: {q.exclude_words}")

    # 演示客户端侧过滤（需要实际搜索结果）
    print("\n  提示: 实际过滤需要 DHT 搜索结果，此处仅展示解析。")
    print("  在 PYaCyNode.search() 中，高级搜索语法自动生效。")


# =============================================================================
# 模式 4: 爬虫 + 本地索引
# =============================================================================
def demo_crawler_indexer():
    """演示 v0.4.1 爬虫与本地索引：抓取网页并索引到 SQLite FTS5。"""
    from pyacy.crawler import SimpleCrawler
    from pyacy.indexer import LocalIndexer

    print("\n" + "=" * 60)
    print("模式 4: 爬虫 + 本地索引")
    print("=" * 60)

    crawler = SimpleCrawler(user_agent="PYaCy-Demo/0.4.1")
    indexer = LocalIndexer()

    # 抓取网页
    test_url = "https://example.com"
    print(f"\n--- 抓取 {test_url} ---")
    result = crawler.fetch(test_url)

    if result.ok:
        print(f"✅ 成功 (HTTP {result.status}, {result.elapsed:.2f}s)")
        print(f"   标题: {result.title}")
        print(f"   文本: {len(result.text)} 字符")
        print(f"   链接: {len(result.links)} 个")

        # 索引到本地
        indexer.add_document(
            url=result.url,
            title=result.title,
            content=result.text,
        )
        print(f"\n--- 索引 ---")
        print(f"   已索引: {result.title}")

        # 搜索本地索引
        hits = indexer.search("example", limit=3)
        print(f"\n--- 本地搜索 'example' ---")
        for i, hit in enumerate(hits, 1):
            print(f"  {i}. {hit['title']} — {hit['url']}")
    else:
        print(f"❌ 抓取失败 (HTTP {result.status}, {result.error})")

    # robots.txt 遵从
    print(f"\n--- robots.txt 遵从 ---")
    cache = crawler.robots_cache
    allowed = cache.is_allowed("https://example.com/some-page", user_agent="PYaCy-Demo/0.4.1")
    print(f"   https://example.com/some-page 允许爬取: {allowed}")

    indexer.close()


# =============================================================================
# 模式 5: RWI Pull — 无需公网 IP 积累本地索引
# =============================================================================
def demo_rwi_pull():
    """演示 RWI Pull 模式：从 Senior 节点主动拉取反向索引数据。"""
    from pyacy import PYaCyNode

    print("\n" + "=" * 60)
    print("模式 5: RWI Pull")
    print("=" * 60)

    node = PYaCyNode(name="pyacy-rwi-demo")
    node.bootstrap(timeout=120)

    stats = node.get_peer_stats()
    if stats.get('senior_peers', 0) == 0:
        print("⚠️  无可用的 Senior 节点，跳过 Pull 演示")
        node.close()
        return

    # 单次 Pull
    print("正在 Pull RWI...")
    imported = node.pull_once(peers=3, word_count=2)
    print(f"导入 {imported} 条 RWI")

    # RWI 统计
    rwi_stats = node.get_rwi_stats()
    print(f"\n--- RWI 统计 ---")
    print(f"  本地 RWI: {rwi_stats['total']} 条")

    # 搜索时自动合并本地 RWI
    if rwi_stats['total'] > 0:
        print("\n--- 搜索（本地 RWI + 远程 DHT） ---")
        results = node.search("python", use_local_rwi=True, count=3)
        for ref in results.references:
            source = "本地" if getattr(ref, 'is_local', False) else "远程"
            print(f"  [{source}] {ref.title[:70]}")

    node.close()


# =============================================================================
# 模式 6: API 适配器 — 统一搜索接口
# =============================================================================
def demo_api_adapter():
    """演示 PYaCyAdapter 统一接口：本地+远程并行搜索，自动路由。"""
    from pyacy import PYaCyAdapter

    print("\n" + "=" * 60)
    print("模式 6: API 适配器")
    print("=" * 60)

    adapter = PYaCyAdapter()
    print("正在引导入网...")
    adapter.bootstrap(timeout=120)

    # 网络状态
    status = adapter.get_network_status()
    print(f"\n--- 网络状态 ---")
    print(f"  已知节点: {status.get('peer_count', 0)}")
    print(f"  RWI: {status.get('rwi_count', 0)} 条")
    print(f"  引导状态: {'✅ 成功' if status.get('bootstrapped') else '⚠️ 失败'}")

    # 统一搜索
    if status.get('bootstrapped'):
        print("\n--- 统一搜索 'python' ---")
        results = adapter.search("python", count=5)
        print(f"  本地: {results.get('local_count', 0)}, 远程: {results.get('remote_count', 0)}")

    adapter.close()


# =============================================================================
# 主入口
# =============================================================================
if __name__ == "__main__":
    print("PYaCy v0.4.1 综合使用示例")
    print("=" * 60)
    print()

    # 模式 1: HTTP 客户端（无需引导，直接测试）
    demo_http_client()

    # 模式 3: 高级搜索语法（纯解析，无需网络）
    demo_advanced_search()

    # 模式 4: 爬虫 + 本地索引（需要网络访问目标 URL）
    demo_crawler_indexer()

    # 以下模式需要 P2P 网络连接，取消注释以启用：
    # demo_p2p_node()
    # demo_rwi_pull()
    # demo_api_adapter()

    print("\n" + "=" * 60)
    print("示例完毕！")
    print("\n💡 提示:")
    print("  - 模式 2/5/6 需要 P2P 网络连接，已默认跳过")
    print("  - 取消 main 中对应行的注释即可启用")
    print("  - 完整文档: https://github.com/RuikangSun/PYaCy#readme")
