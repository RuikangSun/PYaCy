# PYaCy

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)
[![零依赖](https://img.shields.io/badge/dependencies-zero-green)](https://github.com/RuikangSun/PYaCy)

[English](README_EN.md) | 中文

**PYaCy** 是 YaCy 分布式搜索引擎的 Python 客户端库，提供搜索查询、状态监控、爬虫控制、P2P 网络接入和 DHT 分布式搜索等核心功能。仅依赖 Python 标准库，零第三方运行时依赖。

## 特性

- 🔍 **搜索查询** — 支持本地搜索和 P2P 全局搜索
- 🌐 **P2P 网络接入** — 自动引导入网，发现网络节点
- 🤝 **Hello 握手** — 与其他 YaCy 节点交换状态信息
- 📡 **DHT 分布式搜索** — 跨节点分布式哈希表查询
- 🕷️ **爬虫控制** — 启动/管理网页爬虫任务
- 📄 **文档推送** — 将文档直接推送到 YaCy 索引
- 🛡️ **Junior 友好** — 无需公网 IP 即可参与 P2P 网络
- 📦 **零依赖** — 纯 Python 标准库实现（`urllib`），无需安装第三方包

## 快速开始

### 安装

```bash
pip install -e .
```

### 搜索与状态查询

```python
from pyacy import YaCyClient

with YaCyClient("http://localhost:8090") as client:
    # 搜索
    results = client.search("python", resource="global")
    for item in results.items:
        print(f"{item.title} — {item.link}")

    # 节点状态
    status = client.status()
    print(f"索引：{status.index_size} 文档，运行 {status.uptime_hours:.1f} 小时")
```

### P2P 网络接入与分布式搜索

```python
from pyacy import PYaCyNode

# 创建 Junior 节点（无需公网 IP）
node = PYaCyNode(name="my-pyacy-node")
print(f"节点哈希：{node.hash}")

# 从公共种子节点引导入网
node.bootstrap()

# 查看网络统计
stats = node.get_peer_stats()
print(f"已发现 {stats['total_peers']} 个节点")

# DHT 分布式搜索
results = node.search("open source")
for ref in results.references:
    print(ref.url)

node.close()
```

## API 参考

### HTTP 客户端（`YaCyClient`）

| API 端点 | 方法 | 说明 |
|----------|------|------|
| `/yacysearch.json` | `search()` | 搜索查询（本地/P2P） |
| `/suggest.json` | `suggest()` | 搜索建议（自动补全） |
| `/api/status_p.json` | `status()` | 节点运行状态 |
| `/api/version.json` | `version()` | 版本信息 |
| `/Network.json` | `network()` | P2P 网络统计 |
| `/Crawler_p.html` | `crawl_start()` | 启动爬虫任务 |
| `/CrawlStartExpert.html` | `crawl_start_expert()` | 专家模式爬虫 |
| `/api/push_p.json` | `push_document()` | 推送文档到索引 |
| `/IndexDeletion_p.html` | `delete_index()` | 删除索引文档 |
| `/api/blacklists/*` | `get_blacklists()` 等 | 黑名单管理 |

### P2P 网络（`PYaCyNode`）

| 模块 | 类/方法 | 说明 |
|------|---------|------|
| `pyacy.network` | `PYaCyNode` | P2P 节点管理、网络拓扑 |
| `pyacy.p2p.seed` | `Seed` | 节点信息表示与序列化 |
| `pyacy.p2p.protocol` | `P2PProtocol` | P2P 协议编解码 |
| `pyacy.p2p.hello` | `HelloClient` | Hello 握手协议 |
| `pyacy.dht.search` | `DHTSearchClient` | DHT 分布式搜索 |

### 节点类型

| 类型 | 说明 | 公网 IP |
|------|------|:-------:|
| **Junior** | 被动节点，无法接收传入连接 | ❌ 不需要 |
| **Senior** | 主动节点，可接收传入连接 | ✅ 需要 |
| **Principal** | 核心节点，提供网络基础设施 | ✅ 需要 |

PYaCy 默认作为 **Junior** 节点运行。

## 项目结构

```
PYaCy/
├── src/pyacy/
│   ├── __init__.py          # 包入口，导出公共 API
│   ├── client.py            # YaCyClient HTTP 客户端
│   ├── exceptions.py        # 自定义异常层次结构
│   ├── models.py            # 数据模型（SearchResponse 等）
│   ├── utils.py             # 工具函数（Base64、哈希、种子解析）
│   ├── p2p/
│   │   ├── seed.py          # Seed 数据模型
│   │   ├── protocol.py      # P2P 协议层
│   │   └── hello.py         # Hello 协议客户端
│   ├── dht/
│   │   └── search.py        # DHT 搜索客户端
│   └── network.py           # PYaCyNode 网络管理
├── tests/                   # 测试套件（340 个测试）
├── examples/                # 使用示例
├── skills/                  # Agent Skills（AI 助手集成）
├── pyproject.toml
└── LICENSE                  # MIT License
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 运行示例
python examples/basic_usage.py
python examples/p2p_search.py
```

## 开发路线图

### ✅ 已完成

| 里程碑 | 版本 | 说明 |
|--------|------|------|
| HTTP 客户端 | v0.1.0 | 封装 YaCy REST API：搜索、状态、爬虫、推送、黑名单 |
| 数据模型 | v0.1.0 | 类型安全的响应解析（SearchResponse、PeerStatus 等） |
| 异常体系 | v0.1.0 | 7 种自定义异常，覆盖连接/超时/认证/响应错误 |
| P2P 种子模型 | v0.2.0 | Seed 数据模型、YaCy Base64 编解码、种子字符串解析 |
| P2P 协议层 | v0.2.0 | P2PProtocol 编解码、Hello 握手客户端 |
| DHT 分布式搜索 | v0.2.0 | 多节点并行搜索、结果去重与聚合 |
| 网络引导 | v0.2.0 | 从公共种子节点自动 Bootstrap、节点发现 |
| Junior 节点支持 | v0.2.2 | 无公网 IP 环境下完整 P2P 功能 |
| Hello 握手修复 | v0.2.3 | 未压缩种子格式兼容、握手成功率 100% |
| 零依赖 | v0.2.4 | 移除 requests，纯标准库 urllib 实现 |
| DHT 哈希路由 | v0.3.0 | 词哈希 XOR 距离路由、迭代搜索扩展、31 个硬编码种子 |
| 响应解析修复 | v0.3.1 | 修复 resourceN 字段解析、SimpleCoding 解码、新旧格式兼容 |

### 🚧 进行中

| 里程碑 | 说明 |
|--------|------|
| 完善文档 | API 文档、架构说明、贡献指南 |

### 📋 计划中

| 里程碑 | 说明 | 复杂度 |
|--------|------|:------:|
| RWI 索引接收 | 接收并存储其他节点分发的 RWI 引用 | ★★★ |
| kelondro 兼容存储 | 兼容 YaCy Java 版的索引存储格式 | ★★★★ |
| RWI 分发引擎 | 向其他节点分发本地 RWI 引用（需公网 IP） | ★★★★ |
| 内置爬虫 | 独立网页爬虫，构建本地 Solr 索引 | ★★★★ |
| 完整 P2P 节点 | Senior/Principal 节点模式，支持传入连接 | ★★★★★ |
| Web UI | 简易 Web 管理界面 | ★★★ |

> **推荐路径**：当前功能已覆盖日常搜索和 P2P 网络接入需求。下一步建议实现 RWI 索引接收，使 PYaCy 能为 P2P 网络贡献搜索索引。

## 许可证

MIT License — 详见 [LICENSE](LICENSE)。