# PYaCy

[English](README_EN.md) | 中文 | [我是机器人](README_AGENT.md)
**PYaCy** 是 [YaCy](https://yacy.net/) 分布式搜索引擎的 Python 客户端库。它不仅封装了 YaCy REST API，还能直接参与 P2P 分布式网络 — 搜索、爬取、索引、RWI 拉取，零第三方运行时依赖。

> README文档更新时间：2026-05-14

---

## 特性

| 类别 | 功能 | 说明 |
|:---|------|------|
| **搜索** | HTTP 搜索 + DHT 分布式搜索 | 本地/全局/高级搜索语法（`site:` `filetype:` `intitle:` 等） |
| **P2P 网络** | Bootstrap 引导 + 节点发现 | 31 个硬编码种子，自动发现 ~160 个节点 |
| **DHT 路由** | 词哈希 XOR 距离路由 | 迭代搜索扩展，精准定位负责节点 |
| **爬虫** | 内置网页爬虫 | 纯标准库，支持深度/域限制、robots.txt 遵从、按域名限速 |
| **本地索引** | SQLite FTS5 全文索引 | 爬取即索引，支持中文 CJK 分词 |
| **RWI Pull** | 主动拉取 RWI 数据 | 无需公网 IP，从 Senior 节点获取反向索引 |
| **API 适配器** | 统一搜索接口 | 本地 RWI + 远程 DHT 并行查询，无感切换 |
| **零依赖** | 纯 Python 标准库 | `urllib` + `sqlite3` + `html.parser`，pip install 即用 |
| **Agent Skills** | AI 智能体集成 | 5 个 Agent Skill，Claude Code / Cursor 即装即用 |

---

## 快速开始

### 安装

```bash
pip install -e .
```

PYaCy **零运行时依赖**，仅需 Python ≥ 3.9 标准库。

### P2P 节点 — 直接接入 YaCy 网络

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="my-node")
node.bootstrap()

# DHT 分布式搜索
results = node.search("python", count=10)
for ref in results.references:
    print(f"{ref.title} — {ref.url}")

# 高级搜索语法
results = node.search('site:github.com python async', count=10)
results = node.search('filetype:pdf machine learning', count=10)

node.close()
```

### 爬虫 + 本地索引

```python
from pyacy.crawler import SimpleCrawler
from pyacy.indexer import LocalIndexer

crawler = SimpleCrawler()
indexer = LocalIndexer()

# 抓取网页
result = crawler.fetch("https://example.com")
print(f"标题: {result.title}, 文本: {len(result.text)} 字符")

# 索引到本地 SQLite
indexer.add_document(url=result.url, title=result.title, content=result.text)

# 搜索本地索引
hits = indexer.search("example")
for hit in hits:
    print(f"{hit['title']} — {hit['url']}")
```

### RWI Pull — 无需公网 IP 积累本地索引

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="my-node")
node.bootstrap()

# 从 Senior 节点拉取 RWI 数据
imported = node.pull_once()
print(f"导入 {imported} 条 RWI")

# 查看本地 RWI 统计
stats = node.get_rwi_stats()
print(f"本地 RWI: {stats['total']} 条")

# 搜索时自动合并本地 RWI + 远程 DHT
results = node.search("python", use_local_rwi=True)
node.close()
```

### 统一 API 适配器

```python
from pyacy import PYaCyAdapter

adapter = PYaCyAdapter()
adapter.bootstrap()

# 本地 RWI + 远程 DHT 并行搜索
results = adapter.search("python")
print(f"本地: {results['local_count']}, 远程: {results['remote_count']}")

# 网络状态
status = adapter.get_network_status()
print(f"已知节点: {status['peer_count']}")
```

---

## API 参考

### 顶层入口

| 类 | 用途 |
|---|------|
| `YaCyClient` | HTTP 客户端，连接已运行的 YaCy 节点 |
| `PYaCyNode` | P2P 节点，直接接入 YaCy 分布式网络 |
| `PYaCyAdapter` | 统一 API 接口，本地+远程并行搜索 |

### 默认 Junior 节点模式

| 类型 | 说明 | 公网 IP |
|:---|------|:---:|
| **Junior** | 被动节点，无法接收传入连接（**默认**） | 无需 |
| **Senior** | 主动节点，可接收传入连接 | 需要 |
| **Principal** | 核心节点，提供网络基础设施 | 需要 |

### 模块索引

| 模块 | 关键类/函数 | 说明 |
|:---|------|------|
| `pyacy.client` | `YaCyClient` | HTTP 搜索、状态、爬虫控制、文档推送 |
| `pyacy.network` | `PYaCyNode` | P2P 节点生命周期、引导入网、搜索路由 |
| `pyacy.dht.search` | `DHTSearchClient` | DHT 哈希路由、XOR 距离、并行搜索 |
| `pyacy.search.query_parser` | `SearchQuery` | 高级搜索语法解析（site/filetype/intitle 等） |
| `pyacy.rwi.storage` | `RWIStorage` | SQLite FTS5 RWI 存储引擎 |
| `pyacy.rwi.pull` | `RWIPuller` | Pull 模式，主动拉取 RWI |
| `pyacy.crawler.basic` | `SimpleCrawler` | 纯标准库网页抓取 |
| `pyacy.crawler.robots` | `RobotsCache` | robots.txt 解析与遵从 |
| `pyacy.indexer.local` | `LocalIndexer` | SQLite FTS5 本地全文索引 |
| `pyacy.api.adapter` | `PYaCyAdapter` | 统一搜索接口 |
| `pyacy.p2p.seed` | `Seed`, `SeedKeys` | 节点数据模型 |
| `pyacy.p2p.protocol` | `P2PProtocol` | P2P 协议编解码 |
| `pyacy.p2p.hello` | `HelloClient` | Hello 握手协议 |
| `pyacy.p2p.seeds` | `HARDCODED_SEEDS` 等 | 种子管理与三层发现 |
| `pyacy.exceptions` | `PYaCyError` 等 7 种 | 异常层次结构 |
| `pyacy.utils` | `yacy_base64_encode` 等 | Base64、词哈希、XOR 距离 |

---

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行全部测试
pytest tests/ -v

# 仅运行单元测试
pytest tests/ -v --ignore=tests/test_live_network.py --ignore=tests/live_network_test.py

# 代码格式化
black src/ tests/
ruff check src/ tests/
```

### 运行线上 P2P 测试

```bash
# 使用默认种子节点
python tests/test_live_network.py

# 使用自定义种子（如果你的网络有限制）
python tests/test_live_network.py --seeds http://your-reachable-node:8090

# 保守参数（长超时、长间隔）
python tests/test_live_network.py --timeout 45 --delay 2.0
```

---

## 开发路线图

### 已完成

| 里程碑 | 版本 | 说明 |
|:---|:---|------|
| HTTP 客户端 | v0.1.0 | 搜索、状态、爬虫、推送、黑名单 |
| 数据模型 + 异常体系 | v0.1.0 | SearchResponse、PeerStatus 等 + 7 种异常 |
| P2P 种子模型与协议 | v0.2.0 | Seed 编解码、P2PProtocol、Hello 握手 |
| DHT 分布式搜索 | v0.2.0 | 多节点并行搜索、结果去重聚合 |
| 网络引导 | v0.2.0 | 自动 Bootstrap、节点发现 |
| 零依赖 | v0.2.4 | 移除 requests，纯 urllib 实现 |
| DHT 哈希路由 | v0.3.0 | XOR 距离路由、迭代搜索扩展、31 个硬编码种子 |
| 响应解析修复 | v0.3.1 | resourceN 字段、SimpleCoding、新旧格式兼容 |
| 中文兼容性修复 | v0.3.2 | 中文逗号、字段名大小写、缺失字段回退、搜索缓存 |
| RWI 存储 | v0.4.0 | SQLite FTS5 存储引擎、TTL 过期 |
| RWI Pull | v0.4.0 | 主动拉取 RWI（无需公网 IP） |
| 爬虫 + 本地索引 | v0.4.1 | SimpleCrawler + LocalIndexer（SQLite FTS5） |
| 高级搜索语法 | v0.4.1 | site:/filetype:/intitle:/inhtml: 等操作符 |
| robots.txt 遵从 | v0.4.1 | RobotsCache，按域名限速调度 |
| API 适配器 | v0.4.1 | PYaCyAdapter 统一搜索接口 |
| Agent Skills | v0.4.1 | 5 个技能（search/bootstrap/crawler/status/rwi） |

### 进行中 / 计划中

| 里程碑 | 说明 | 复杂度 |
|:---|------|:---:|
| Senior 节点模式 | 端口监听、传入连接、DHT 路由表维护、RWI 分发引擎 | ★★★★★ |
| GUI 界面 | Flet + pyecharts 跨平台图形界面 | ★★★★ |
| kelondro 兼容存储 | 兼容 YaCy Java 版的索引存储格式 | ★★★★ |
| Web UI | 简易 Web 管理界面 | ★★★ |

---

## 许可证

MIT License — 详见 [LICENSE](LICENSE)。