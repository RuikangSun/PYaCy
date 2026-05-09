---
name: pyacy-status
description: >
  查询 PYaCy 节点运行状态、P2P 网络连接信息和索引统计。
  当用户询问"节点状态"、"网络状态"、"索引数量"、"P2P 连接数"时使用此技能。
  v0.4.0 新增: RWI 存储统计、本地索引统计。
  关键词触发: 状态、网络状态、节点信息、P2P状态、索引数量。
license: MIT
compatibility: Python 3.10+, PYaCy>=0.4.0
metadata:
  category: monitoring
  requires_local_yacy: partial
---

# PYaCy 节点状态查询

查询 PYaCy 节点的运行状态、P2P 网络连接信息和索引统计数据。

## 功能概览

| 功能 | 说明 |
|------|------|
| **P2P 节点状态** | 节点池规模、连接状态、引导信息 |
| **RWI 存储统计** | 本地 RWI 条目数、词哈希数、URL 数 |
| **本地索引统计** | 本地爬取索引的文档数 |
| **YaCy 服务状态** (需本地 YaCy) | 运行状态、内存、版本、网络统计 |

## P2P 节点状态

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="my-node")
node.bootstrap()

stats = node.get_peer_stats()
print(f"总节点数: {stats['total_peers']}")
print(f"Senior 节点: {stats['senior_peers']}")
print(f"已引导: {stats['is_bootstrapped']}")
print(f"类型分布: {stats.get('type_distribution', {})}")

node.close()
```

## RWI 存储统计（v0.4.0）

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="my-node")
node.bootstrap()

rwi_stats = node.get_rwi_stats()
print(f"本地 RWI 条目: {rwi_stats['total']}")
print(f"独立 URL 数: {rwi_stats['unique_urls']}")
print(f"独立词哈希数: {rwi_stats['unique_word_hashes']}")

node.close()
```

## 使用 PYaCyAdapter

```python
from pyacy import PYaCyAdapter

adapter = PYaCyAdapter()
adapter.bootstrap()

status = adapter.get_network_status()
print(f"已知节点: {status['peer_count']}")
print(f"RWI 条目: {status['rwi_count']}")
print(f"已引导: {status['is_bootstrapped']}")

adapter.close()
```

## YaCy 服务状态（需要本地 YaCy）

```python
from pyacy import YaCyClient

client = YaCyClient("http://localhost:8090")
status = client.status()
print(f"状态: {status.status}")
print(f"运行时间: {status.uptime_hours:.1f} 小时")
print(f"索引文档数: {status.index_size}")

network = client.network()
print(f"活跃节点: {network.active_peers}")
print(f"网络总 URL: {network.total_urls:,}")

client.close()
```

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `PYaCyConnectionError` | YaCy 服务未启动 | 启动 YaCy 或检查 URL |
| `total_peers=0` | 未引导入网 | 先调用 `node.bootstrap()` |
| `rwi_count=0` | 未执行 Pull | 先调用 `node.pull_once()` |
