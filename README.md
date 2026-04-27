# PYaCy

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)

**PYaCy** 是 YaCy 分布式搜索引擎的 Python 客户端库。

提供搜索查询、状态监控、爬虫控制、文档索引等核心功能的类型安全 API。

## 快速开始

```bash
pip install -e .
```

```python
from pyacy import YaCyClient

with YaCyClient("http://localhost:8090") as client:
    # 搜索
    results = client.search("python", resource="global")
    for item in results.items:
        print(f"{item.title} — {item.link}")

    # 状态
    status = client.status()
    print(f"索引: {status.index_size} 文档, 运行 {status.uptime_hours:.1f} 小时")
```

## 已实现的功能（Level 0）

| API                    | 方法                    | 说明                 |
|------------------------|------------------------|----------------------|
| `/yacysearch.json`     | `search()`             | 搜索查询（本地/P2P） |
| `/suggest.json`        | `suggest()`            | 搜索建议（自动补全） |
| `/api/status_p.json`   | `status()`             | 节点运行状态         |
| `/api/version.json`    | `version()`            | 版本信息             |
| `/Network.json`        | `network()`            | P2P 网络统计         |
| `/Crawler_p.html`      | `crawl_start()`        | 启动爬虫任务         |
| `/CrawlStartExpert.html` | `crawl_start_expert()` | 专家模式爬虫         |
| `/api/push_p.json`     | `push_document()`      | 推送文档到索引       |
| `/IndexDeletion_p.html` | `delete_index()`      | 删除索引文档         |
| `/api/blacklists/*`    | `get_blacklists()` 等  | 黑名单管理           |

## 项目结构

```
PYaCy/
├── README.md
├── LICENSE              # MIT
├── pyproject.toml
├── src/pyacy/
│   ├── __init__.py      # 包入口，导出公共 API
│   ├── client.py        # YaCyClient HTTP 客户端
│   ├── exceptions.py    # 自定义异常层次结构
│   └── models.py        # 数据模型类
├── tests/
│   ├── conftest.py      # 测试夹具与模拟数据
│   └── test_client.py   # 客户端测试套件
└── examples/
    └── basic_usage.py   # 基本使用示例
```

## 开发

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## 许可证

MIT License — 详见 [LICENSE](LICENSE)。
