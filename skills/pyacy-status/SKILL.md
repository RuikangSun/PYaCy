---
name: pyacy-status
description: >
  查询 YaCy 节点运行状态、P2P 网络连接信息和索引统计。
  当用户询问"节点状态"、"网络状态"、"YaCy 是否在线"、"索引数量"、"P2P 连接数"时使用此技能。
license: MIT
compatibility: Python 3.9+, PYaCy>=0.2.0
metadata:
  category: monitoring
  requires_local_yacy: partial
---

# PYaCy 节点状态查询

查询 YaCy 搜索节点的运行状态、P2P 网络连接信息和索引统计数据。

## 功能概览

| 功能 | 依赖 | 返回信息 |
|------|------|----------|
| **YaCy 服务状态** (HTTP 客户端) | 本地 YaCy 服务器 | 运行状态、内存、索引、版本、网络统计 |
| **PYaCy P2P 状态** (P2P 网络) | 无（纯 P2P 节点） | 节点池规模、连接状态、引导信息 |

## YaCy 服务状态（HTTP 客户端模式，需本地 YaCy）

```python
from pyacy import YaCyClient

client = YaCyClient("http://localhost:8090")

# 节点运行状态
status = client.status()
print(f"状态: {status.status}")
print(f"运行时间: {status.uptime_hours:.1f} 小时")
print(f"内存使用: {status.memory_used_mb:.0f} MB")
print(f"索引文档数: {status.index_size}")

# 版本信息
version = client.version()
print(f"版本: {version.version}")
print(f"Java: {version.java_version}")

# P2P 网络统计
network = client.network()
print(f"活跃节点: {network.active_peers}")
print(f"网络总 URL: {network.total_urls:,}")

client.close()
```

## PYaCy P2P 节点状态（P2P 网络模式）

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="my-node")
node.bootstrap()

# 节点池统计
stats = node.get_peer_stats()
print(f"总节点数: {stats['total_peers']}")
print(f"Senior 节点: {stats['senior_peers']}")
print(f"已引导: {stats['is_bootstrapped']}")

# 节点类型分布
print(f"类型分布: {stats['type_distribution']}")

node.close()
```

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `PYaCyConnectionError` | YaCy 服务未启动 | 启动 YaCy 或检查 URL |
| `PYaCyTimeoutError` | 网络延迟过高 | 增大 timeout 参数 |
| `total_peers=0` | 未引导入网 | 先调用 `node.bootstrap()` |
