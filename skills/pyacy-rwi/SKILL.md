---
name: pyacy-rwi
description: >
  使用 PYaCy 的 RWI（反向词索引）存储和 Pull 模式，实现本地 RWI 索引管理。
  当需要从 YaCy P2P 网络拉取 RWI 数据、查询本地 RWI 存储、管理本地索引时使用此技能。
  关键词触发: RWI、拉取、pull、本地索引、反向词索引、索引存储、导入RWI。
license: MIT
compatibility: >
  Python 3.10+, PYaCy>=0.4.0, 无需公网 IP (Junior Pull 模式)。
  PYaCy 仓库: https://github.com/RuikangSun/PYaCy
metadata:
  level: 2
  category: indexer
  requires_bootstrap: true
  network_access: true
---

# PYaCy RWI — 反向词索引存储与 Pull 模式

## 何时使用此技能

**必须使用本技能的场景**：
- 需要从 YaCy P2P 网络拉取 RWI 数据到本地存储
- 查询本地 RWI 存储中的索引条目
- 管理本地 RWI 数据库（统计、清理过期条目）
- 用户说"导入 RWI"、"Pull 模式"、"本地索引"
- AI Agent 需要积累本地搜索索引以提升后续搜索质量

**不需要本技能的场景**：
- 仅执行远程 DHT 搜索 → 使用 `pyacy-search` 技能
- 仅连接 P2P 网络 → 使用 `pyacy-bootstrap` 技能
- 管理本地网页索引（爬虫抓取的内容） → 使用 `pyacy-crawler` 技能

## 前置条件

1. 已安装 PYaCy 包: `pip install pyacy`
2. PYaCy 节点已完成网络引导（Bootstrap）
3. 网络能访问至少一个 Senior 节点

## Pull 模式原理

Pull 模式是 PYaCy 的独创特性，解决了无公网 IP 节点无法被动接收 RWI 的问题：

```
传统 Push 模式（需要公网 IP）:
  Senior A → 计算词哈希 → 找到负责节点 B → Push RWI 到 B
  (B 必须有公网 IP，否则 A 无法连接到 B)

PYaCy Pull 模式（无需公网 IP）:
  Junior C → 主动向 Senior 查询特定词哈希 → 获取 RWI → 存储到本地
  (C 发起传出连接，无需公网 IP)
```

Pull 的数据来源是 Senior 节点的 RWI 存储。Senior 节点在网络中承担以下责任：
1. 存储被 DHT 路由到自己的 RWI 条目
2. 响应其他节点的搜索请求（包括 Pull 请求）
3. 参与 DHT 索引分发

## 核心工作流程

### 步骤 1: 创建节点并引导入网

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="my-agent-node")
node.bootstrap()
print(f"已发现 {node.peer_count} 个节点")
```

### 步骤 2: 执行 RWI Pull

```python
# 单次 Pull — 从 Senior 节点拉取 RWI
imported = node.pull_once(
    peers=3,           # 查询的 Senior 节点数
    word_count=3,      # 查询的词哈希数
    timeout_ms=2000,   # 每次查询超时（毫秒）
)
print(f"导入 {imported} 条 RWI")
```

### 步骤 3: 查看本地 RWI 统计

```python
stats = node.get_rwi_stats()
print(f"本地 RWI 条目: {stats['total']}")
print(f"独立 URL 数: {stats['unique_urls']}")
print(f"独立词哈希数: {stats['unique_word_hashes']}")
```

### 步骤 4: 使用本地 RWI 搜索

```python
# 搜索时自动并行查询本地 RWI + 远程 DHT
results = node.search("python", use_local_rwi=True)
print(f"本地命中: {results.local_hits}")
print(f"远程命中: {results.remote_hits}")
print(f"总引用数: {len(results.references)}")
```

## 高级用法

### 使用 PYaCyAdapter 统一接口

```python
from pyacy import PYaCyAdapter

adapter = PYaCyAdapter()
adapter.bootstrap()

# Pull RWI
imported = adapter.pull_rwi()

# 统一搜索（本地 + 远程）
results = adapter.search("ShanghaiTech University")
print(results['total'], results['local_count'], results['remote_count'])
```

### 直接操作 RWIStorage

```python
from pyacy.rwi import RWIStorage, RWIEntry

storage = RWIStorage("~/.pyacy/rwi.db")

# 手动写入 RWI 条目
entry = RWIEntry(
    word_hash="abcDEF",
    url_hash="ghiJKL",
    url="https://example.com",
    title="示例页面",
    source="manual",
)
storage.insert(entry)

# 按词哈希查询
results = storage.query_by_word_hash("abcDEF")
for r in results:
    print(r.url, r.title)

# 全文搜索
hits = storage.fulltext_search("示例")
for h in hits:
    print(h.url, h.title)

# 统计
print(storage.get_stats())

# 清理过期条目
storage.cleanup_expired()
storage.close()
```

## Pull 策略参数

| 参数 | 默认值 | 说明 |
|------|:------:|------|
| `peers` | 5 | 每次 Pull 查询的 Senior 节点数 |
| `word_count` | 3 | 每次 Pull 查询的词哈希数 |
| `timeout_ms` | 8000 | 每次查询的超时（毫秒） |

**建议**：
- `peers=3` 足够覆盖大多数场景，增大不会线性提升结果
- `word_count=3` 使用高频英文词哈希作为种子，过大增加延迟
- Pull 操作建议每 5-10 分钟执行一次，避免频繁请求

## 常见错误与处理

| 错误 | 原因 | 处理 |
|------|------|------|
| `imported=0` | Senior 节点无目标词的 RWI | 正常现象，换词哈希重试 |
| Pull 超时 | 网络延迟 | 增大 `timeout_ms` 或减少 `peers` |
| `RWIStorage` 锁定 | 多进程同时写入 | 确保单进程访问 |
| 本地搜索无结果 | 本地 RWI 为空 | 先执行 `pull_once()` 导入数据 |

## 注意事项

- **Pull 模式不保证成功**: Senior 节点可能没有特定词哈希的 RWI
- **TTL 过期**: 默认 24 小时，过期条目自动清理
- **存储位置**: 默认 `~/.pyacy/rwi.db`，SQLite 格式
- **CJK 支持**: 中文文本自动预分词，支持单字检索
