---
name: pyacy-crawler
description: >
  使用 PYaCy 控制 YaCy 爬虫进行网页抓取与索引管理。
  当需要抓取网页内容、将文档加入搜索索引、管理爬虫任务或删除已索引内容时使用此技能。
  关键词触发: 爬虫、抓取、索引、crawl、爬取、收录、索引管理、黑名单。
license: MIT
compatibility: >
  Python 3.9+, PYaCy>=0.2.3, 本地运行 YaCy 服务 (http://localhost:8090)。
  爬虫功能需要 YaCy 服务器端支持，为 Level 0 HTTP 客户端功能。
  PYaCy 仓库: https://github.com/pyacy/pyacy
metadata:
  level: 0
  category: crawler
  requires_bootstrap: false
  requires_yacy_server: true
  network_access: true
---

# PYaCy 爬虫 — 网页抓取与索引管理

## 何时使用此技能

**必须使用本技能的场景**：
- 抓取指定 URL 的网页内容并加入 YaCy 索引
- 管理爬虫任务（启动/暂停/查看状态）
- 通过 API 推送文档到本地索引
- 删除索引中的特定文档
- 管理黑名单（阻止特定 URL 被索引）
- AI Agent 需要将外部内容收录到本地搜索引擎

**不需要本技能的场景**：
- 仅搜索已索引内容 → 使用 `pyacy-search` 技能
- 连接 P2P 网络 → 使用 `pyacy-bootstrap` 技能

## 前置条件

1. 本地运行 YaCy 搜索服务器（默认端口 8090）
2. 已安装 PYaCy 包: `pip install pyacy`
3. 如果 YaCy 启用了认证，需要提供用户名密码

## 创建客户端

```python
from pyacy import YaCyClient

# 基本客户端
client = YaCyClient("http://localhost:8090")

# 带认证的客户端
client = YaCyClient(
    "http://localhost:8090",
    auth=("admin", "your-password"),
)

# 使用上下文管理器（自动关闭连接）
with YaCyClient("http://localhost:8090") as client:
    # 在此执行爬虫操作
    pass
```

## 核心工作流程

### 抓取单个网页

```python
# 基础抓取 — 爬取 URL 及其链接（深度 0 = 仅当前页面）
result = client.crawl_start(
    url="https://example.com/article",
    depth=0,
    recrawl="nodouble",  # 不重复爬取
)

# 检查抓取状态
status = client.status()
print(f"索引大小: {status.index_size}")
print(f"URL 队列: {status.local_url_count}")
```

### 专家模式抓取

```python
# 精细控制爬取参数
result = client.crawl_start_expert(
    start_url="https://example.com",
    depth=2,                       # 爬取深度
    must_match="example.com/.*",   # 仅爬取匹配的 URL
    must_not_match=".*\\.pdf",     # 排除 PDF 文件
    recrawl="nodouble",
    crawler_count=4,               # 爬虫线程数
)
```

### 推送文档到索引

```python
# 通过 API 直接推送文档（不经过爬虫）
response = client.push_document(
    url="https://example.com/my-page",
    title="页面标题",
    content="页面的完整文本内容...",
    author="作者名",
    tags=["标签1", "标签2", "标签3"],
)
# response includes: success, message, url_hash
```

### 删除索引文档

```python
# 按 URL 删除
client.delete_index(url="https://example.com/old-page")

# 按 URL 哈希删除
client.delete_index(url_hash="abc123def456")

# 按关键词匹配删除
client.delete_index(keyword_match="spam-content")
```

### 黑名单管理

```python
# 获取所有黑名单条目
blacklists = client.get_blacklists()
for entry in blacklists.entries:
    print(f"{entry.host} — {entry.reason}")

# 添加黑名单
client.add_blacklist(
    host="spam-domain.com",
    path="/spam/.*",
    reason="垃圾内容",
)

# 删除黑名单条目
client.delete_blacklist(entry_id="some-entry-id")
```

## 使用示例

### 完整流程: 抓取 → 索引 → 搜索

```python
from pyacy import YaCyClient
import time

with YaCyClient("http://localhost:8090") as client:
    # 1. 抓取网页
    print("开始抓取...")
    client.crawl_start("https://example.com", depth=1)

    # 2. 等待爬虫完成（生产环境应轮询 status()）
    time.sleep(10)

    # 3. 确认索引状态
    status = client.status()
    print(f"已索引 {status.index_size} 个文档")

    # 4. 搜索验证
    results = client.search("example", resource="local")
    print(f"找到 {results.total_results} 条结果")
```

### 批量推送文档

```python
from pyacy import YaCyClient

documents = [
    {
        "url": "https://example.com/doc1",
        "title": "文档 1",
        "content": "这是第一份文档的内容...",
    },
    {
        "url": "https://example.com/doc2",
        "title": "文档 2",
        "content": "这是第二份文档的内容...",
    },
]

with YaCyClient("http://localhost:8090") as client:
    for doc in documents:
        try:
            response = client.push_document(**doc)
            print(f"✅ {doc['title']}: {response.message}")
        except Exception as e:
            print(f"❌ {doc['title']}: {e}")
```

## API 参考表

| 方法 | 端点 | 说明 |
|------|------|------|
| `crawl_start(url, depth, ...)` | `/Crawler_p.html` | 启动基础爬虫 |
| `crawl_start_expert(start_url, ...)` | `/CrawlStartExpert.html` | 专家模式爬虫 |
| `push_document(url, title, content, ...)` | `/api/push_p.json` | 推送文档到索引 |
| `delete_index(url=, url_hash=, keyword_match=)` | `/IndexDeletion_p.html` | 删除索引文档 |
| `get_blacklists()` | `/api/blacklists/list.json` | 获取黑名单 |
| `add_blacklist(host, path, reason)` | `/api/blacklists/add.json` | 添加黑名单 |
| `delete_blacklist(entry_id)` | `/api/blacklists/delete.json` | 删除黑名单条目 |

## 常见错误与处理

| 错误 | 原因 | 处理 |
|------|------|------|
| `PYaCyConnectionError` | YaCy 服务未启动 | 确认 YaCy 在 localhost:8090 运行 |
| `PYaCyAuthError` (401/403) | 需要认证 | 提供 auth 参数 |
| 爬虫不执行 | URL 已被索引 | 设置 `recrawl="reload"` |
| `push_document` 失败 | 文档内容为空 | 确保 content 参数非空 |
| 黑名单添加失败 | 正则语法错误 | 检查 path 参数的正则表达式 |

## 注意事项

- **爬虫功能依赖 YaCy 服务器端**: 需要本地运行或可访问远程 YaCy 实例
- **速率控制**: 避免过于频繁地抓取同一站点，遵守 robots.txt
- **索引持久化**: 通过 push_document 推送的文档在 YaCy 重启后依然存在
- **URL 去重**: YaCy 自动跳过已索引的 URL（可通过 `recrawl` 参数控制）
- **安全**: 不要抓取或索引包含敏感信息的内部页面
