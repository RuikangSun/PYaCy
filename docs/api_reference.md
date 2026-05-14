# API 参考

## 顶层模块

### `from pyacy import YaCyClient`

HTTP 客户端，连接已运行的 YaCy 节点的 REST API。

```python
with YaCyClient("http://localhost:8090", password="admin") as client:
    results = client.search("python", resource="global", count=20)
    status = client.status()
    version = client.version()
    network = client.network()
    client.crawl_start("https://example.com", depth=2)
    client.push_document("https://example.com/page", "<html>...</html>")
```

### `from pyacy import PYaCyNode`

P2P 网络管理器，接入 YaCy 分布式网络。

```python
node = PYaCyNode(name="my-node")
node.bootstrap(timeout=120)              # 引导入网
results = node.search("python", count=10) # DHT 搜索
imported = node.pull_once()               # Pull RWI
stats = node.get_rwi_stats()              # RWI 统计
node.close()
```

### `from pyacy import PYaCyAdapter`

统一接口，供 GUI / Agent / 外部程序调用。

```python
from pyacy import PYaCyAdapter

adapter = PYaCyAdapter()
adapter.bootstrap()

# 统一搜索（本地 RWI + 远程 DHT 并行）
results = adapter.search("python", use_local_rwi=True, count=10)

# 网络状态
status = adapter.get_network_status()

# 爬虫 + 索引
adapter.crawl_and_index("https://example.com")

# RWI Pull
imported = adapter.pull_rwi()

adapter.close()
```

---

## 高级搜索语法 (`pyacy.search`)

### `SearchQuery`（v0.4.1）

解析 YaCy 高级搜索语法，分离操作符和纯文本，支持客户端侧过滤。

```python
from pyacy.search import SearchQuery

# 解析查询
q = SearchQuery('site:github.com filetype:pdf python async')
print(q.site)         # "github.com"
print(q.filetype)     # "pdf"
print(q.effective_query)  # "python async"（纯文本部分，用于 DHT 搜索）

# 支持的操作符
q = SearchQuery('site:edu filetype:pdf intitle:"machine learning" author:john python')
q = SearchQuery('/language/en /date python')
q = SearchQuery('python -java -perl')  # 排除词
q = SearchQuery('"exact phrase" python')  # 短语搜索
q = SearchQuery('intitle:python intitle:tutorial')  # 标题邻近搜索
q = SearchQuery('inhtml:python')  # HTML 内容搜索

# 客户端侧过滤（搜索结果返回后）
filtered = q.filter(dht_results.references)
for ref in filtered:
    print(ref.url, ref.title)
```

**支持的操作符完整列表**：

| 操作符 | 格式 | 说明 | 实现位置 |
|:---|:---|------|:---|
| `site:` | `site:github.com` | 按域名过滤 | 客户端过滤 |
| `filetype:` | `filetype:pdf` | 按文件扩展名过滤 | 客户端过滤 |
| `intitle:` | `intitle:python` | 标题包含关键词 | 客户端过滤 |
| `inhtml:` | `inhtml:python` | 标记（YaCy 语义，实际在 DHT 中效果有限） | DHT 路由 |
| `author:` | `author:john` | 作者名 | 客户端过滤 |
| `/language/` | `/language/en` | 按语言过滤 | 客户端过滤 |
| `/http` `/https` | `/https` | 按协议过滤 | 客户端过滤 |
| `/date` | `/date` | 按日期排序 | 客户端排序 |
| `-word` | `-java` | 排除包含特定词的页面 | 客户端过滤 |
| `"phrase"` | `"machine learning"` | 精确短语匹配 | DHT 路由 |

### `SearchQuery.filter()` 方法

```python
# 返回过滤后的 DHTReference 列表
filtered = q.filter(references)
```

内部逐条检查：
1. `_match_site(url, site)` — URL 域名匹配
2. `_match_filetype(url, ext)` — URL 扩展名匹配
3. `_match_protocol(url, protocol)` — 协议匹配
4. `_match_intitle(ref, keywords)` — 标题关键词匹配
5. `_match_author(ref, author)` — 作者字段匹配
6. `_apply_near(refs, keywords)` — 邻近关键词匹配
7. `_apply_recent(refs)` — 优先近期结果
8. `_apply_sort(refs)` — 按日期排序

---

## RWI 模块 (`pyacy.rwi`)

### `RWIStorage`

SQLite FTS5 RWI 存储引擎。

```python
from pyacy.rwi import RWIStorage

storage = RWIStorage("~/.pyacy/rwi.db")

# 写入
from pyacy.rwi import RWIEntry
entry = RWIEntry(
    word_hash="abcDEF",
    url_hash="xyz789",
    url="https://example.com",
    title="Example",
    snippet="A short description...",
)
storage.insert(entry)

# 查询
results = storage.query_by_word_hash("abcDEF")
results = storage.fulltext_search("python")
count = storage.count()
stats = storage.get_stats()

# 删除
storage.delete_by_url_hash("ghiJKL")
storage.delete_by_word_hash("abcDEF")
storage.cleanup_expired()  # 清理过期条目（TTL=86400s）

storage.close()
```

### `RWIPuller`

Pull 模式 RWI 拉取器 — 无需公网 IP，主动从 Senior 节点拉取。

```python
from pyacy.rwi import RWIPuller

puller = RWIPuller(node, storage)

# 单次 Pull
imported = puller.pull_once(
    word_hashes=None,     # 使用默认高频词哈希
    peers=5,              # 拉取的 Senior 节点数
    word_count=3,         # 每个节点拉取的词数
    timeout=8000,         # 超时（毫秒）
)

# 后台定期 Pull
puller.start_periodic_pull(interval=300)  # 每 5 分钟
puller.stop_periodic_pull()

# 统计
total = puller.total_pulled
```

---

## 爬虫模块 (`pyacy.crawler`)

### `SimpleCrawler`

纯标准库网页爬虫，无第三方依赖。

```python
from pyacy.crawler import SimpleCrawler

crawler = SimpleCrawler(user_agent="MyBot/1.0", timeout=15)

# 单页抓取
result = crawler.fetch("https://example.com")
print(result.url)       # 最终 URL（跟随重定向后）
print(result.title)     # 页面标题
print(result.text)      # 纯文本内容
print(result.html)      # 原始 HTML
print(result.links)     # 提取的链接列表（list[str]）
print(result.status)    # HTTP 状态码
print(result.elapsed)   # 请求耗时（秒）
print(result.ok)        # 是否成功

# 递归爬取
results = crawler.crawl(
    start_url="https://example.com",
    max_depth=2,
    max_pages=10,
    domain_limit="example.com",  # 可选域限制
)
for r in results:
    print(f"{r.url}: {len(r.links)} links")
```

**属性**：

| 属性 | 类型 | 说明 |
|:---|:---|------|
| `robots_cache` | `RobotsCache` | robots.txt 遵从缓存 |
| `rate_limiter` | `_RateLimiter` | 按域名限速（默认 1 req/s） |

### `RobotsCache`（v0.4.1）

robots.txt 解析与遵从，实现 RFC 9309 子集。

```python
from pyacy.crawler import RobotsCache

cache = RobotsCache()
allowed = cache.is_allowed("https://example.com/page", user_agent="MyBot/1.0")
delay = cache.get_crawl_delay("https://example.com")
```

---

## 本地索引模块 (`pyacy.indexer`)

### `LocalIndexer`

SQLite FTS5 本地全文索引，支持中文 CJK 分词。

```python
from pyacy.indexer import LocalIndexer

indexer = LocalIndexer("~/.pyacy/index.db")

# 添加文档
indexer.add_document(
    url="https://example.com",
    title="示例页面",
    content="这是页面内容...",
    tags=["example", "demo"],
)

# 批量添加
docs = [
    {"url": "https://a.com", "title": "A", "content": "..."},
    {"url": "https://b.com", "title": "B", "content": "..."},
]
indexer.add_documents(docs)

# 搜索
results = indexer.search("示例", limit=10)
for hit in results:
    print(hit["title"], hit["url"], hit["snippet"])

# 统计
count = indexer.count()

indexer.close()
```

---

## DHT 搜索模块 (`pyacy.dht`)

### `DHTSearchClient`

DHT 哈希路由搜索客户端。

```python
from pyacy.dht import DHTSearchClient, DHTReference

client = DHTSearchClient(protocol)

# 搜索
result = client.fulltext_search("python", peers=seed_list, count=10)
for ref in result.references:
    print(ref.url, ref.title, ref.snippet)
    print(ref.size, ref.word_count, ref.language)

print(f"搜索时间: {result.searchtime}ms")
print(f"本地 RWI 命中: {result.local_hits}")
print(f"远程 RWI 命中: {result.remote_hits}")

# 分页
result.page(offset=10, count=10)  # 获取第二页
```

### `DHTReference`

搜索结果条目。

| 字段 | 类型 | 说明 |
|------|------|------|
| `url_hash` | str | URL 哈希（YaCy Base64） |
| `url` | str | 网页 URL |
| `title` | str | 页面标题 |
| `snippet` | str | 摘要/描述 |
| `size` | int | 页面大小（字节） |
| `word_count` | int | 词数 |
| `language` | str | 语言代码 |
| `last_modified` | int | 最后修改时间戳 |

---

## P2P 协议层 (`pyacy.p2p`)

### `Seed`

节点种子数据模型。

```python
from pyacy.p2p import Seed, SeedKeys

seed = Seed.create_junior(name="my-node", port=8090)
print(seed.hash)          # YaCy Base64 哈希
print(seed.base_url)      # "http://ip:port"
print(seed.is_senior())   # False
print(seed.dna[SeedKeys.IP])  # IP 地址
```

### `HelloClient`

Hello 握手协议客户端。

```python
from pyacy.p2p import HelloClient

client = HelloClient(my_seed, timeout=30)

# 单节点握手
remote_seed = client.hello_single("http://senior-node:8090")

# 网络发现
discovered = client.discover_network(seed_list, max_peers=100)
```

### `P2PProtocol`

底层协议编解码（HTTP multipart）。

```python
from pyacy.p2p import P2PProtocol

protocol = P2PProtocol(my_seed, timeout=15)

# 编码请求
body = protocol.encode_search_request("python", count=10)

# 解码响应
result_dict = protocol.parse_search_response(response_body)
```

---

## 工具函数 (`pyacy.utils`)

```python
from pyacy.utils import (
    yacy_base64_encode,     # 字节 → YaCy Base64 字符串
    yacy_base64_decode,     # YaCy Base64 字符串 → 字节
    word_to_hash,           # 单词 → YaCy 词哈希
    words_to_hash_query,    # 多词 → 哈希查询参数
    dht_distance,           # XOR 距离计算
)
```

---

## 异常层次

```
PYaCyError (基类)
├── PYaCyConnectionError   # 连接失败
├── PYaCyTimeoutError      # 超时
├── PYaCyResponseError     # 响应格式错误
├── PYaCyAuthError         # 认证失败
├── PYaCyServerError       # 服务器错误
├── PYaCyValidationError   # 参数验证失败
└── PYaCyP2PError          # P2P 网络错误
```
