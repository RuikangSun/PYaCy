---
name: pyacy-search
description: >
  使用 PYaCy 通过 YaCy P2P 分布式搜索引擎进行网页全文搜索。
  当需要搜索互联网内容、查找网页、获取不依赖单一搜索引擎的搜索结果时使用此技能。
  支持 DHT 分布式搜索（多节点并行）、本地索引搜索、全局搜索。
  关键词触发: 搜索、查找、检索、search、网页搜索、P2P搜索、分布式搜索。
license: MIT
compatibility: >
  Python 3.9+, PYaCy>=0.2.3 (pip install pyacy), 无需公网 IP (Junior 模式)。
  PYaCy 仓库: https://github.com/pyacy/pyacy
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
- 用户说"用 PYaCy 搜索"、"用 YaCy 搜一下"

**不需要本技能的场景**：
- 只是查看节点状态 → 使用 `pyacy-status` 技能
- 只是连接 P2P 网络 → 使用 `pyacy-bootstrap` 技能

## 前置条件

1. 已安装 PYaCy 包: `pip install pyacy`
2. PYaCy 节点已完成网络引导（Bootstrap），即 `node.is_bootstrapped == True`
3. 已知节点池中至少有一个可连接的 Senior/Principal 节点

如果节点尚未引导，先执行:
```python
from pyacy import PYaCyNode
node = PYaCyNode(name="my-agent-node")
node.bootstrap()
```

## 核心工作流程

### 步骤 1: 确认节点已引导

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="my-agent-node")

if not node.is_bootstrapped:
    success = node.bootstrap()
    if not success:
        raise RuntimeError("无法接入 P2P 网络，检查种子节点是否可达")
```

### 步骤 2: 执行搜索

```python
# 基础 DHT 搜索（推荐）
result = node.search(
    query="搜索关键词",
    count=20,           # 期望结果数
    max_peers=5,        # 最多搜索的节点数
    language="zh",      # 语言过滤（zh/en/de/fr/...）
)

# 访问结果
for ref in result.references:
    print(f"标题: {ref.title}")
    print(f"URL: {ref.url}")
    print(f"描述: {ref.description}")
```

### 步骤 3: 解读搜索结果

`DHTSearchResult` 包含:
- `success`: 搜索是否成功
- `references`: DHTReference 列表（url_hash, title, description, url, ranking）
- `links`: 纯 URL 字符串列表
- `link_count`: 总链接数
- `join_count`: 参与搜索的 P2P 节点数
- `search_time_ms`: 搜索耗时

**重要**: 如果 `references` 中的 `title` 为空，说明远端节点返回的是 RWI 引用（仅 URL 哈希），
需要进一步获取摘要。可以在 `search()` 中添加 `abstracts=True` 参数。

## 高级搜索用法

### 在指定节点上搜索

```python
target_seed = list(node.peers.values())[0]  # 获取第一个已知节点
result = node.search_on_peer(target_seed, "精确搜索词", count=10)
```

### 排除特定词

```python
result = node.search(
    "python programming",
    exclude_words=["snake", "monty"],
)
```

### 仅获取链接（不获取摘要，更快）

```python
from pyacy.dht import DHTSearchClient

search_client = DHTSearchClient(node._protocol)
result = search_client.fulltext_search(
    peers=list(node.peers.values()),
    my_hash=node.hash,
    query="关键词",
    count=20,
    abstracts=False,   # 不请求摘要，仅返回 URL 哈希引用
)
```

## 本地索引搜索（HTTP 客户端模式，需本地 YaCy 实例）

如果本地运行了 YaCy 服务:

```python
from pyacy import YaCyClient

with YaCyClient("http://localhost:8090") as client:
    # 本地搜索
    results = client.search("python", resource="local", maximum_records=20)
    for item in results.items:
        print(f"{item.title} — {item.link}")

    # 全局搜索（通过本地 YaCy 代理 P2P 搜索）
    global_results = client.search("open source", resource="global", maximum_records=20)
```

## 搜索策略建议

1. **优先 DHT 搜索**: 无需运行本地 YaCy，纯 P2P 参与
2. **多节点并行**: `max_peers=5` 可在速度与覆盖率之间取得平衡
3. **语言过滤**: 中文使用 `language="zh"`，英文使用 `language="en"`
4. **排除词**: 歧义词用 `exclude_words` 过滤，提升精准度
5. **结果去重**: DHT 搜索结果已自动按 `url_hash` 去重

## 常见错误与处理

| 错误 | 原因 | 处理 |
|------|------|------|
| `PYaCyP2PError: 无可用于搜索的节点` | 未调用 bootstrap() | 先调用 `node.bootstrap()` |
| 搜索结果为空 | 所有目标节点不可达 | 检查网络连接，尝试其他种子节点 |
| `references` 中 title 为空 | 节点仅返回 RWI 引用 | 设置 `abstracts=True` 获取摘要 |
| 搜索超时 | 网络延迟较高 | 减少 `max_peers`，增大 `timeout` |

## 注意事项

- **无公网 IP 友好**: PYaCy 默认以 Junior 身份运行，通过 Senior 节点代理搜索
- **结果时效性**: 搜索结果取决于 P2P 网络中各节点的索引状态
- **去重机制**: 相同 URL 哈希的引用自动合并
- **并发限制**: 避免短时间内大量搜索请求，可能被对端限流
