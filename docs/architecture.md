# 架构说明

## 整体架构

PYaCy 采用分层架构，从底层到顶层：

```
┌──────────────────────────────────────────────────────────────────┐
│  API 适配层 (api/adapter.py)                                     │
│  统一接口，供 GUI / Agent / 外部程序调用                           │
├──────────────────────────────────────────────────────────────────┤
│  应用层                                                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ ┌─────────┐ │
│  │YaCyClient│ │PYaCyNode │ │SimpleCrwl│ │LocalIdx │ │SearchQry│ │
│  │HTTP客户端│ │P2P网络管理│ │网页爬虫  │ │本地索引  │ │高级语法  │ │
│  └──────────┘ └──────────┘ └──────────┘ └─────────┘ └─────────┘ │
├──────────────────────────────────────────────────────────────────┤
│  核心层                                                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │DHTSearch │ │RWIStorage│ │RWIPuller │ │RobotsCh │            │
│  │DHT哈希路由│ │SQLite存储│ │Pull模式  │ │robots.txt│            │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘            │
├──────────────────────────────────────────────────────────────────┤
│  协议层 (p2p/)                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                        │
│  │ Protocol │ │  Hello   │ │  Seeds   │                        │
│  │协议编解码│ │握手协议  │ │种子管理  │                        │
│  └──────────┘ └──────────┘ └──────────┘                        │
├──────────────────────────────────────────────────────────────────┤
│  基础层                                                           │
│  urllib + sqlite3 + json + gzip + hashlib + html.parser + re    │
│  （Python 标准库，零外部依赖）                                     │
└──────────────────────────────────────────────────────────────────┘
```

## 核心数据流

### DHT 搜索流程

```
用户查询 "python"
    ↓
分词 → ["python"]
    ↓
词哈希 → hash("python") → YaCy Base64
    ↓
哈希路由 → 在已知节点中按 XOR 距离排序
         → 取距离最近的 k 个节点（负责节点）
    ↓
并发查询 → 向 k 个节点发送 /yacysearch.html 请求
    ↓
响应解析 → 解码 resourceN 字段（SimpleCoding: b|base64 / p|plain）
    ↓
结果合并 → 去重 + 排序 + 返回 DHTSearchResult
```

### 高级搜索过滤流程

```
用户查询 'site:github.com filetype:pdf python async'
    ↓
SearchQuery 解析
    ├─ 提取操作符 → site="github.com", filetype="pdf"
    └─ 提取纯文本 → effective_query="python async"
    ↓
effective_query → 分词 → 词哈希 → DHT 哈希路由 → 远程搜索
    ↓
获取原始 DHT 结果（包含完整 URL）
    ↓
客户端侧过滤（SearchQuery.filter()）
    ├─ _match_site()      → URL 域名匹配 site 操作符
    ├─ _match_filetype()  → URL 扩展名匹配 filetype 操作符
    ├─ _match_protocol()  → URL 协议匹配 /http /https 操作符
    ├─ _match_intitle()   → 标题中包含 intitle: 关键词
    ├─ _match_author()    → 作者字段匹配 author: 操作符
    ├─ _apply_near()      → intitle: 关键词邻近匹配
    ├─ _apply_recent()    → 优先近期结果
    └─ _apply_sort()      → /date 按日期排序
    ↓
返回过滤后的结果
```

**为什么在客户端侧过滤？**

YaCy 的 DHT 搜索端点（`/yacysearch.html`）本身不支持高级搜索操作符（`site:` `filetype:` 等）。
因此 PYaCy 采用两步策略：
1. 用**纯文本部分**（不含操作符）执行 DHT 搜索，获取尽可能多的候选结果
2. 在**客户端侧**根据操作符过滤结果，提供与 YaCy HTTP API 一致的搜索体验

### RWI Pull 流程

```
Pull 触发（手动或定时）
    ↓
选择词哈希 → 高频英文词（the, and, of）+ 本地已有词哈希
    ↓
选择节点 → 基于 DHT 哈希路由找 XOR 距离最近的 Senior（DEFAULT_PULL_PEERS=5）
    ↓
并发拉取 → 对每个 (词哈希, 节点) 对发送 /yacysearch.html（DEFAULT_PULL_TIMEOUT_MS=8000）
    ↓
解析响应 → 提取 resourceN 中的 url_hash, url, title → RWIEntry
    ↓
写入 SQLite → RWIStorage.insert() → FTS5 索引
```

### 爬虫 → 索引流程

```
用户指定种子 URL（或多个）
    ↓
SimpleCrawler.fetch(url)
    ├─ robots.txt 检查（RobotsCache.is_allowed()）
    ├─ 按域名限速（_rate_limiter）
    ├─ HTTP GET → urllib
    ├─ 状态码检查（200-299）
    ├─ Content-Type 过滤（text/html）
    └─ HTML 解析（html.parser）→ CrawlResult(title, text, links, ...)
    ↓
LocalIndexer.add_document(url, title, content)
    ├─ CJK 预分词（中文/日文/韩文字符间插空格）
    └─ SQLite FTS5 INSERT
    ↓
LocalIndexer.search(query)
    └─ SQLite FTS5 MATCH → 返回命中列表
```

### 种子发现流程

```
启动
    ↓
加载种子来源（三层冗余）:
    1. 本地缓存 seed_cache.json
    2. 硬编码种子 HARDCODED_SEEDS（30 个精选节点）
    3. 在线种子 seedlist.json
    ↓
并行探测 → HTTP GET /api/status_p.json（5s 超时，20 并发）
    ↓
筛选 → Senior/Principal + 在线 ≥24h + 索引 ≥500
    ↓
排序 → 按延迟排序，保留前 30 个
    ↓
Hello 握手 → 向可达种子发送 multipart POST
    ↓
seedlist.json 扩展 → 从可达种子获取更多节点
    ↓
更新路由表 → 保存到本地缓存
```

---

## 模块依赖关系

```
p2p.seed (Seed 数据模型) ← 被所有模块引用
    ↑
p2p.protocol (P2P 协议编解码)
    ↑
p2p.hello (Hello 握手) ← p2p.seeds (种子发现)
    ↑
dht.search (DHTSearchClient, _tokenize_query) ← search.query_parser (SearchQuery)
    ↑
network (PYaCyNode) ← rwi.pull (RWIPuller) ← rwi.storage (RWIStorage)
    ↑
api.adapter (PYaCyAdapter)  ← crawler (SimpleCrawler) → indexer (LocalIndexer)
    ↑
client (YaCyClient) — 独立模块，不依赖其他 pyacy 子模块
```

---

## 设计决策

### 为什么 Junior 节点可以搜索？

YaCy DHT 的搜索本质上是**向负责节点查询词哈希对应的 RWI**，不需要查询者自身存储任何 RWI。Junior 节点只需：

1. 知道网络中的节点列表（通过 seedlist 获取）
2. 能计算词哈希到节点的 XOR 距离（纯计算）
3. 向负责节点发送搜索请求（HTTP 传出连接）

以上三点都不需要公网 IP。

### Pull 模式解决什么问题？

传统 YaCy 中，RWI 通过 Push 模式分发（Senior A → 负责节点 B）。但 Junior 节点无法接收 Push（无公网 IP）。Pull 模式反转了这个过程：Junior 主动向 Senior 查询特定词哈希的 RWI，将结果存储到本地，从而积累本地索引。

### 为什么高级搜索需要客户端侧过滤？

YaCy 的 DHT 搜索端点（`/yacysearch.html`）以词哈希为基础单位路由请求，不支持 `site:` `filetype:` 等高级搜索操作符的语义处理。而 YaCy HTTP API（`/yacysearch.json`）由 YaCy 服务器端统一处理。由于 PYaCy 在 P2P 模式下不经过本地 YaCy 服务器，高级搜索操作符需要在客户端侧实现。

**实现策略**：
- 解析阶段：`SearchQuery` 解析原始查询字符串，分离操作符和纯文本
- 搜索阶段：`DHTSearchClient.fulltext_search()` 使用纯文本（`effective_query`）执行 DHT 搜索
- 过滤阶段：`SearchQuery.filter()` 在结果返回后根据操作符逐条过滤

### 本地索引 vs RWI 存储的区别

| 维度 | 本地索引 (LocalIndexer) | RWI 存储 (RWIStorage) |
|:---|------|------|
| **数据来源** | 本地爬虫抓取的网页全文 | 远程 Senior 节点的 RWI 引用 |
| **存储内容** | `url + title + content（全文）` | `word_hash + url_hash + url + title + snippet` |
| **索引方式** | SQLite FTS5（unicode61 + CJK 预分词） | SQLite FTS5（unicode61） |
| **查询方式** | 直接全文搜索 | 按词哈希查询 + 全文搜索 |
| **TTL** | 无（手动管理） | 86400s（24h）自动过期 |
