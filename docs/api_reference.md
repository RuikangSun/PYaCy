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

---

## RWI 模块 (`pyacy.rwi`)

### `RWIStorage`

SQLite FTS5 RWI 存储引擎。

```python
from pyacy.rwi import RWIStorage

storage = RWIStorage("~/.pyacy/rwi.db")

# 写入
from pyacy.rwi import RWIEntry
entry = RWIEntry(word_hash="abcDEF", url="https://example.com", title="Example")
storage.insert(entry)

# 查询
results = storage.query_by_word_hash("abcDEF")
results = storage.fulltext_search("python")
count = storage.count()
stats = storage.get_stats()

# 删除
storage.delete_by_url_hash("ghiJKL")
storage.delete_by_word_hash("abcDEF")
storage.cleanup_expired()  # 清理过期条目

storage.close()
```

### `RWIPuller`

Pull 模式 RWI 拉取器。

```python
from pyacy.rwi import RWIPuller

puller = RWIPuller(node, storage)

# 单次 Pull
imported = puller.pull_once(peers=3, word_count=3)

# 后台定期 Pull
puller.start_periodic_pull(interval=300)  # 每 5 分钟
puller.stop_periodic_pull()
```

---

## 爬虫模块 (`pyacy.crawler`)

### `SimpleCrawler`

单页面爬虫。

```python
from pyacy.crawler import SimpleCrawler

crawler = SimpleCrawler(user_agent="MyBot/1.0", timeout=15)
result = crawler.fetch("https://example.com")

print(result.url)       # 最终 URL（跟随重定向后）
print(result.title)     # 页面标题
print(result.text)      # 纯文本内容
print(result.html)      # 原始 HTML
print(result.links)     # 提取的链接列表
print(result.status)    # HTTP 状态码
print(result.elapsed)   # 请求耗时（秒）
print(result.ok)        # 是否成功
```

---

## 本地索引模块 (`pyacy.indexer`)

### `LocalIndexer`

SQLite FTS5 本地全文索引。

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

# 搜索
results = indexer.search("示例", limit=10)
for hit in results:
    print(hit.title, hit.url, hit.snippet)

# 统计
count = indexer.count()

indexer.close()
```

---

## API 适配器 (`pyacy.api`)

### `PYaCyAdapter`

统一接口，供 GUI / Agent / 外部程序调用。

```python
from pyacy import PYaCyAdapter

adapter = PYaCyAdapter()
adapter.bootstrap()

# 统一搜索（本地 RWI + 远程 DHT 并行）
results = adapter.search("python", use_local_rwi=True, count=10)
# → {"total": 25, "local_count": 3, "remote_count": 22, "results": [...]}

# 网络状态
status = adapter.get_network_status()
# → {"peer_count": 160, "senior_count": 155, "rwi_count": 54, ...}

# 爬虫 + 索引
adapter.crawl_and_index("https://example.com")
local_results = adapter.search_local("example")

# RWI Pull
imported = adapter.pull_rwi()

adapter.close()
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
```

### `DHTReference`

搜索结果条目。

| 字段 | 类型 | 说明 |
|------|------|------|
| `url_hash` | str | URL 哈希 |
| `url` | str | 网页 URL |
| `title` | str | 页面标题 |
| `snippet` | str | 摘要 |
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

底层协议编解码。

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
    yacy_base64_encode,
    yacy_base64_decode,
    word_to_hash,
    words_to_hash_query,
    dht_distance,
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
