---
name: pyacy-crawler
description: >
  使用 PYaCy 进行网页抓取与本地索引管理。
  v0.4.0 新增: 内置简易爬虫（无需 YaCy 服务器）和 SQLite FTS5 本地全文索引。
  同时保留对 YaCy 服务器爬虫 API 的支持（需本地 YaCy 实例）。
  当需要抓取网页内容、构建本地搜索索引时使用此技能。
  关键词触发: 爬虫、抓取、索引、crawl、爬取、收录、索引管理。
license: MIT
compatibility: >
  Python 3.10+, PYaCy>=0.4.0, 无需公网 IP。
  本地爬虫和索引功能无需 YaCy 服务器。
  PYaCy 仓库: https://github.com/RuikangSun/PYaCy
metadata:
  level: 2
  category: crawler
  requires_bootstrap: false
  network_access: true
---

# PYaCy 爬虫 — 网页抓取与本地索引管理

## 何时使用此技能

**必须使用本技能的场景**：
- 抓取指定 URL 的网页内容
- 将抓取的内容索引到本地全文搜索
- 用户说"抓取这个网页"、"爬取并索引"
- AI Agent 需要将外部内容收录到本地搜索引擎

**不需要本技能的场景**：
- 仅搜索已索引内容 → 使用 `pyacy-search` 技能
- 连接 P2P 网络 → 使用 `pyacy-bootstrap` 技能
- 管理 RWI 数据 → 使用 `pyacy-rwi` 技能

## 两种模式

| 模式 | 说明 | 需要 YaCy |
|------|------|:---------:|
| **内置爬虫** (v0.4.0) | SimpleCrawler + LocalIndexer，纯 Python 实现 | ❌ |
| **YaCy 服务器爬虫** | 通过 HTTP API 控制 YaCy 爬虫 | ✅ |

## 内置爬虫模式（推荐，无需 YaCy 服务器）

### 抓取单个网页

```python
from pyacy.crawler import SimpleCrawler

crawler = SimpleCrawler(timeout=15)
result = crawler.fetch("https://example.com")

if result.ok:
    print(f"URL: {result.url}")
    print(f"标题: {result.title}")
    print(f"文本: {result.text[:200]}")
    print(f"链接数: {len(result.links)}")
    print(f"耗时: {result.elapsed:.1f}s")
```

### 索引到本地全文搜索

```python
from pyacy.crawler import SimpleCrawler
from pyacy.indexer import LocalIndexer

crawler = SimpleCrawler()
indexer = LocalIndexer("~/.pyacy/index.db")

# 抓取并索引
result = crawler.fetch("https://example.com")
if result.ok:
    indexer.add_document(
        url=result.url,
        title=result.title,
        content=result.text,
        tags=["example"],
    )

# 搜索本地索引
hits = indexer.search("关键词", limit=10)
for hit in hits:
    print(f"{hit.title} — {hit.url}")
    print(f"  摘要: {hit.snippet}")

indexer.close()
```

### 使用 PYaCyAdapter（推荐）

```python
from pyacy import PYaCyAdapter

adapter = PYaCyAdapter()

# 爬取并索引（一行代码）
adapter.crawl_and_index("https://example.com")

# 搜索本地索引
results = adapter.search_local("关键词")
print(f"找到 {results['total']} 条结果")
```

## YaCy 服务器爬虫模式（需要本地 YaCy）

```python
from pyacy import YaCyClient

with YaCyClient("http://localhost:8090") as client:
    # 启动爬虫
    client.crawl_start("https://example.com", depth=1)

    # 推送文档
    client.push_document(
        url="https://example.com/page",
        title="页面标题",
        content="页面内容...",
    )

    # 删除索引
    client.delete_index(url="https://example.com/old-page")
```

## 常见错误与处理

| 错误 | 原因 | 处理 |
|------|------|------|
| `fetch` 返回 `ok=False` | URL 不可达 | 检查 URL 和网络连接 |
| 搜索无结果 | 本地索引为空 | 先抓取并索引内容 |
| 爬取慢 | 目标站点响应慢 | 增大 `timeout` 参数 |

## 注意事项

- **速率控制**: 遵守 robots.txt 礼仪，默认 1 秒爬取延迟
- **存储位置**: 默认 `~/.pyacy/index.db`，SQLite 格式
- **CJK 支持**: 中文内容自动预分词，支持单字检索
