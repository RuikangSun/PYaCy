---
name: pyacy-search
description: >
  使用 PYaCy 通过 YaCy P2P 分布式搜索引擎进行网页全文搜索。
  当需要搜索互联网内容、查找网页、获取不依赖单一搜索引擎的搜索结果时使用此技能。
  支持 DHT 分布式搜索（多节点并行）、本地 RWI 索引搜索、全局搜索。
  v0.4.0 新增: 本地 RWI + 远程 DHT 并行搜索，提升搜索命中率。
  关键词触发: 搜索、查找、检索、search、网页搜索、P2P搜索、分布式搜索。
license: MIT
compatibility: >
  Python 3.10+, PYaCy>=0.4.0, 无需公网 IP (Junior 模式)。
  PYaCy 仓库: https://github.com/RuikangSun/PYaCy
metadata:
  level: 2
  category: search
  requires_bootstrap: true
  network_access: true
---

# PYaCy 搜索 — 分布式网页全文搜索

## 何时使用此技能

**必须使用本技能的场景**（任一满足即可）：
- 用户要求搜索网页内容（"帮我搜索 XXX"）
- 用户需要不依赖 Google/Bing 的替代搜索方案
- 用户提到 P2P 搜索、分布式搜索、去中心化搜索
- 用户是 AI Agent，需要自主搜索互联网内容

**不需要本技能的场景**：
- 只是查看节点状态 → 使用 `pyacy-status` 技能
- 只是连接 P2P 网络 → 使用 `pyacy-bootstrap` 技能
- 需要导入 RWI 数据 → 使用 `pyacy-rwi` 技能

## 前置条件

1. 已安装 PYaCy 包: `pip install pyacy`
2. PYaCy 节点已完成网络引导（Bootstrap）
3. 已知节点池中至少有一个可连接的 Senior/Principal 节点

如果节点尚未引导，先执行:
```python
from pyacy import PYaCyNode
node = PYaCyNode(name="my-agent-node")
node.bootstrap()
```

## 核心工作流程

### 步骤 1: 创建节点并引导入网

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="my-agent-node")
if not node.is_bootstrapped:
    node.bootstrap()
```

### 步骤 2: 执行搜索

```python
# DHT 分布式搜索（默认并行查询本地 RWI + 远程节点）
result = node.search(
    query="ShanghaiTech University",
    count=10,           # 期望结果数
    max_peers=20,       # 最多搜索的节点数（v0.4.0 默认 20）
    use_local_rwi=True, # 同时查询本地 RWI（v0.4.0 新增）
)

for ref in result.references:
    print(f"标题: {ref.title}")
    print(f"URL: {ref.url}")
    print(f"摘要: {ref.snippet}")
    print(f"语言: {ref.language}, 大小: {ref.size}")
```

### 步骤 3: 解读搜索结果

`DHTSearchResult` 包含:
- `references`: DHTReference 列表（url, title, snippet, size, word_count, language）
- `links`: 纯 URL 字符串列表
- `searchtime`: 搜索耗时（毫秒）
- `local_hits`: 本地 RWI 命中数（v0.4.0 新增）
- `remote_hits`: 远程 DHT 命中数（v0.4.0 新增）
- `peer_count`: 参与搜索的节点数
- `join_count`: 参与搜索的节点数（兼容字段）

## 高级搜索用法

### 使用 PYaCyAdapter（推荐）

```python
from pyacy import PYaCyAdapter

adapter = PYaCyAdapter()
adapter.bootstrap()

# 统一搜索 — 自动并行本地 RWI + 远程 DHT
results = adapter.search("python", count=10)
print(f"总计: {results['total']}, 本地: {results['local_count']}, 远程: {results['remote_count']}")
```

### 在指定节点上搜索

```python
target_seed = list(node.peers.values())[0]
result = node.search_on_peer(target_seed, "精确搜索词", count=10)
```

### 仅搜索本地 RWI

```python
from pyacy.indexer import LocalIndexer

indexer = LocalIndexer()
hits = indexer.search("关键词", limit=10)
for hit in hits:
    print(hit.title, hit.url, hit.snippet)
```

## 搜索策略建议

1. **默认启用本地 RWI**: `use_local_rwi=True` 并行查询，不会增加延迟
2. **多节点并行**: `max_peers=20` 覆盖更多 DHT 哈希范围
3. **结果去重**: DHT 搜索结果已自动按 URL 去重
4. **Pull 提升**: 搜索前先 `node.pull_once()` 可积累本地 RWI，提升后续搜索命中率

## 常见错误与处理

| 错误 | 原因 | 处理 |
|------|------|------|
| `PYaCyP2PError: 无可用于搜索的节点` | 未调用 bootstrap() | 先调用 `node.bootstrap()` |
| 搜索结果为空 | 节点不可达或无 RWI | 检查网络连接，尝试 Pull 积累本地数据 |
| 搜索慢（>30s） | 部分节点超时 | 减少 `max_peers` 或增大 timeout |
| `references` 中 title 为空 | 节点仅返回 RWI 引用 | 正常现象，后续版本改进 |

## 注意事项

- **无公网 IP 友好**: PYaCy 默认以 Junior 节点运行，通过 Senior 节点代理搜索
- **结果时效性**: 取决于 P2P 网络中各节点的索引状态
- **并发限制**: 避免短时间内大量搜索请求
