# PYaCy [![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)

**PYaCy** 是 YaCy 分布式搜索引擎的 Python 客户端库。

提供搜索查询、状态监控、爬虫控制、P2P 网络接入和 DHT 分布式搜索等核心功能的类型安全 API。

## 快速开始

### 安装

```bash
pip install -e .
```

### Level 0 - HTTP 客户端

```python
from pyacy import YaCyClient

with YaCyClient("http://localhost:8090") as client:
    # 搜索
    results = client.search("python", resource="global")
    for item in results.items:
        print(f"{item.title} — {item.link}")
    
    # 状态查询
    status = client.status()
    print(f"索引：{status.index_size} 文档，运行 {status.uptime_hours:.1f} 小时")
```

### Level 2 - P2P 节点与 DHT 搜索

```python
from pyacy import PYaCyNode, Seed

# 创建 P2P 节点（默认 Junior 类型，无需公网 IP）
node = PYaCyNode(name="my-pyacy-node")
print(f"节点哈希：{node.hash}")

# 添加已知种子节点
seed_str = "p|{Hash=abc123,Port=8090,PeerType=senior,IP=10.0.0.1}"
seed = node.add_peer("http://10.0.0.1:8090", seed_str)

# 查看网络统计
stats = node.get_peer_stats()
print(f"总节点数：{stats['total_peers']}")
print(f"Senior 节点数：{stats['senior_peers']}")

# DHT 搜索（需要已连接到 P2P 网络）
# results = node.search("hello world")
# for ref in results.references:
#     print(ref.url)

# 清理
node.close()
```

## 已实现的功能

### Level 0 - HTTP 客户端

| API | 方法 | 说明 |
|-----|------|------|
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

### Level 2 - P2P 网络与 DHT

| 模块 | 功能 | 说明 |
|------|------|------|
| `pyacy.network` | `PYaCyNode` | P2P 节点管理、网络拓扑 |
| `pyacy.p2p.seed` | `Seed` | 节点信息表示、序列化 |
| `pyacy.p2p.protocol` | `P2PProtocol` | P2P 协议编解码 |
| `pyacy.p2p.hello` | `HelloClient` | Hello 握手协议 |
| `pyacy.dht.search` | `DHTSearchClient` | DHT 分布式搜索 |

## 项目结构

```
PYaCy/
├── README.md
├── LICENSE                 # MIT License
├── pyproject.toml
├── pytest.ini              # pytest 配置
├── src/pyacy/
│   ├── __init__.py         # 包入口，导出公共 API
│   ├── client.py           # YaCyClient HTTP 客户端 (Level 0)
│   ├── exceptions.py       # 自定义异常层次结构
│   ├── models.py           # 数据模型类
│   ├── utils.py            # 工具函数 (Base64、哈希、种子解析)
│   ├── p2p/
│   │   ├── __init__.py
│   │   ├── seed.py         # Seed 数据模型
│   │   ├── protocol.py     # P2P 协议层
│   │   └── hello.py        # Hello 协议客户端
│   ├── dht/
│   │   ├── __init__.py
│   │   └── search.py       # DHT 搜索客户端
│   └── network.py          # PYaCyNode 网络管理
├── tests/
│   ├── conftest.py         # 测试夹具与模拟数据
│   ├── test_client.py      # Level 0 客户端测试
│   ├── test_utils.py       # 工具函数测试
│   ├── test_seed.py        # Seed 模型测试
│   └── test_p2p.py         # P2P/DHT 测试
└── examples/
    ├── basic_usage.py      # Level 0 基本示例
    └── level2_p2p_search.py # Level 2 示例
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 运行示例
python examples/basic_usage.py
python examples/level2_p2p_search.py
```

## 核心设计

### 节点类型

- **Junior**: 被动节点，无法接收传入连接（适合无公网 IP 用户）
- **Senior**: 主动节点，可接收传入连接（需要公网 IP）
- **Principal**: 核心节点，提供网络基础设施

PYaCy 默认作为 **Junior** 节点运行，无需公网 IP 即可参与 P2P 网络。

### 协议实现

- **Hello 协议**: 节点间握手和状态交换
- **DHT 搜索**: 分布式哈希表查询
- **RWI 传输**: 搜索结果传输

### 安全特性

- 所有 P2P 通信使用盐值（salt）验证
- 节点哈希基于身份字符串计算
- 支持种子字符串的压缩编码

## 许可证

MIT License — 详见 [LICENSE](LICENSE)。
