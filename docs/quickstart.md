# 快速开始

## 安装

```bash
git clone https://github.com/RuikangSun/PYaCy.git
cd PYaCy
pip install -e .
```

PYaCy **零运行时依赖**，仅需 Python ≥ 3.9 标准库。

---

## 2种使用模式

### 模式 1：P2P 网络（直接接入 YaCy 分布式网络）

```python
from pyacy import PYaCyNode

# 创建节点并引导入网
node = PYaCyNode(name="my-pyacy")
node.bootstrap()  # 发现 ~160 个节点，约 30-60 秒

# DHT 分布式搜索
results = node.search("ShanghaiTech University", count=10)
for ref in results.references:
    print(f"{ref.title} — {ref.url}")

print(f"搜索耗时: {results.searchtime}ms, 参与节点: {results.peer_count}")
node.close()
```

### 模式 2：统一 API 适配器

```python
from pyacy import PYaCyAdapter

adapter = PYaCyAdapter()
adapter.bootstrap()

# 本地 RWI + 远程 DHT 并行搜索
results = adapter.search("python", count=10)
print(f"本地命中: {results['local_count']}, 远程命中: {results['remote_count']}")

# 网络状态
status = adapter.get_network_status()
print(f"已知节点: {status['peer_count']}, RWI: {status['rwi_count']}")

# 爬虫 + 索引
result = adapter.crawl_and_index("https://example.com")

adapter.close()
```

---

## 高级搜索语法

p>PYaCy 支持 YaCy 兼容的高级搜索操作符，在客户端侧过滤 DHT 搜索结果：

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="my-node")
node.bootstrap()

# 按站点过滤
results = node.search("site:github.com python async", count=10)

# 按文件类型过滤
results = node.search("filetype:pdf machine learning", count=10)

# 组合操作符
results = node.search('site:edu filetype:pdf intitle:"machine learning"', count=10)

# 按语言过滤
results = node.search("/language/en python", count=10)

# 排除词
results = node.search("python -java -perl", count=10)

# 按协议过滤（仅 HTTPS）
results = node.search("/https security", count=10)

# 按日期排序
results = node.search("/date python", count=10)

node.close()
```

**支持的操作符**：

| 操作符 | 示例 | 说明 |
|:---|:---|------|
| `site:` | `site:github.com` | 按域名过滤 |
| `filetype:` | `filetype:pdf` | 按文件扩展名过滤 |
| `intitle:` | `intitle:python` | 标题包含关键词 |
| `author:` | `author:john` | 按作者过滤 |
| `/language/` | `/language/en` | 按语言过滤 |
| `/http` `/https` | `/https` | 按协议过滤 |
| `/date` | `/date` | 按日期排序 |
| `-word` | `-java` | 排除包含某词的页面 |

---

## 网页爬虫 + 本地索引

```python
from pyacy.crawler import SimpleCrawler
from pyacy.indexer import LocalIndexer

crawler = SimpleCrawler()
indexer = LocalIndexer()

# 单页抓取
result = crawler.fetch("https://example.com")
print(f"标题: {result.title}")
print(f"文本长度: {len(result.text)} 字符")
print(f"提取链接: {len(result.links)} 个")

# 索引到本地 SQLite
indexer.add_document(
    url=result.url,
    title=result.title,
    content=result.text,
)

# 递归爬取（深度=2，最多 10 页，限定域名）
results = crawler.crawl(
    start_url="https://example.com",
    max_depth=2,
    max_pages=10,
    domain_limit="example.com",
)

# 批量索引
for r in results:
    indexer.add_document(url=r.url, title=r.title, content=r.text)
    print(f"已索引: {r.title}")

# 搜索本地索引
hits = indexer.search("example", limit=10)
for hit in hits:
    print(f"{hit['title']} — {hit['url']}")

indexer.close()
```

### robots.txt 遵从

```python
from pyacy.crawler import RobotsCache

cache = RobotsCache()

# 检查 URL 是否允许爬取
allowed = cache.is_allowed("https://example.com/private", user_agent="MyBot/1.0")
print(f"允许爬取: {allowed}")

# 获取爬取延迟建议
delay = cache.get_crawl_delay("https://example.com")
print(f"建议延迟: {delay}s")
```

---

## RWI 本地存储与 Pull 模式

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="my-pyacy")
node.bootstrap()

# 启动 Pull 模式 — 主动从 Senior 节点拉取 RWI
imported = node.pull_once(peers=5, word_count=3)
print(f"导入 {imported} 条 RWI")

# 查看本地 RWI 统计
stats = node.get_rwi_stats()
print(f"本地存储: {stats['total']} 条")

# 搜索时自动合并本地 RWI + 远程 DHT
results = node.search("python", use_local_rwi=True)
for ref in results.references:
    print(f"[{'本地' if ref.is_local else '远程'}] {ref.title}")

node.close()
```

---

## 直接使用底层模块

```python
from pyacy.rwi import RWIStorage
from pyacy.crawler import SimpleCrawler
from pyacy.indexer import LocalIndexer
from pyacy.search import SearchQuery

# 解析高级搜索
q = SearchQuery('site:github.com filetype:pdf python')
print(q.effective_query)  # "python"
print(q.site)             # "github.com"

# 按关键词过滤搜索结果
filtered = q.filter(dht_references)
```

---

## 无代码使用：示例脚本

```bash
# 基本 HTTP 搜索
python examples/basic_usage.py

# P2P 网络搜索
python examples/p2p_search.py
```
