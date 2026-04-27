# -*- coding: utf-8 -*-
"""PYaCy 基本使用示例。

本文件展示了 YaCyClient 的核心用法，
包括搜索、状态查询、文档推送等功能。

运行前请确保：
    1. YaCy 服务已启动（默认在 http://localhost:8090）
    2. 安装了依赖: pip install -e .
"""

from pyacy import YaCyClient

# ---------------------------------------------------------------------------
# 1. 创建客户端
# ---------------------------------------------------------------------------
# 默认连接本地 YaCy 实例
client = YaCyClient("http://localhost:8090")

# 如果 YaCy 启用了认证:
# client = YaCyClient("http://localhost:8090", auth=("admin", "password"))

# ---------------------------------------------------------------------------
# 2. 检查连接
# ---------------------------------------------------------------------------
print("=" * 60)
print("检查 YaCy 服务连接...")
if client.ping():
    print("✅ YaCy 服务连接成功！")
else:
    print("❌ 无法连接到 YaCy 服务，请确认服务已启动。")
    exit(1)

# ---------------------------------------------------------------------------
# 3. 获取版本和状态信息
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("YaCy 节点信息")
print("-" * 60)

version = client.version()
print(f"  版本: YaCy {version.version} (SVN r{version.svn_revision})")
print(f"  Java: {version.java_version}")
print(f"  构建日期: {version.build_date}")

status = client.status()
print(f"\n  状态: {status.status}")
print(f"  运行时间: {status.uptime_hours:.1f} 小时")
print(f"  内存使用: {status.memory_used_mb:.0f} MB")
print(f"  索引文档数: {status.index_size}")

# ---------------------------------------------------------------------------
# 4. P2P 网络信息
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("P2P 网络统计")
print("-" * 60)

network = client.network()
print(f"  本节点: {network.peer_name} ({network.peer_hash[:12]}...)")
print(f"  活跃节点: {network.active_peers}")
print(f"  被动节点: {network.passive_peers}")
print(f"  网络总 URL: {network.total_urls:,}")

# ---------------------------------------------------------------------------
# 5. 执行搜索
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("搜索结果（本地索引）")
print("-" * 60)

results = client.search("python", resource="local", maximum_records=5)
print(f"  查询: {results.query}")
print(f"  结果总数: {results.total_results}")
print(f"  当前页: {results.start_index // results.items_per_page + 1} / {results.total_pages}")

if results.items:
    print(f"\n  前 {len(results.items)} 条结果:")
    for i, item in enumerate(results.items, 1):
        print(f"    {i}. {item.title}")
        print(f"       {item.link}")
else:
    print("  (没有找到结果)")

# ---------------------------------------------------------------------------
# 6. 获取搜索建议
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("搜索建议")
print("-" * 60)

suggestions = client.suggest("python")
print(f"  'python' 的建议:")
for s in suggestions.suggestions[:5]:
    print(f"    → {s.word}")

# ---------------------------------------------------------------------------
# 7. 全文搜索（需要在 P2P 网络中）
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("全局搜索（P2P 网络）")
print("-" * 60)

try:
    global_results = client.search(
        "open source",
        resource="global",
        maximum_records=5,
        verify="false",  # 加速搜索
    )
    print(f"  查询: {global_results.query}")
    print(f"  全局结果: {global_results.total_results}")
    if global_results.items:
        for item in global_results.items[:3]:
            print(f"    - {item.title[:60]}...")
except Exception as e:
    print(f"  全局搜索失败: {e}")

# ---------------------------------------------------------------------------
# 8. 使用上下文管理器（自动清理连接）
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("所有示例执行完毕。")

# 显式关闭（如果不用上下文管理器）
client.close()
