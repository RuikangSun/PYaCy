# PYaCy Agent Skills 参考文档

本文档为 AI Agent 提供 PYaCy 的深层技术背景，
按需加载到上下文中，避免主 SKILL.md 过长。

## PYaCy 架构概览

```
┌──────────────────────────────────────────────────────────┐
│                      AI Agent                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  │
│  │pyacy-    │ │pyacy-    │ │pyacy-    │ │pyacy-      │  │
│  │search    │ │bootstrap │ │status    │ │crawler     │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬─────┘  │
│       │             │            │              │        │
├───────┼─────────────┼────────────┼──────────────┼────────┤
│       ▼             ▼            ▼              ▼        │
│  ┌─────────────────────────────────────────────────┐    │
│  │                  PYaCy Library                    │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │    │
│  │  │ Level 0  │ │ Level 2  │ │ Level 2          │ │    │
│  │  │ HTTP     │ │ P2P      │ │ DHT Search       │ │    │
│  │  │ Client   │ │ Network  │ │ Engine           │ │    │
│  │  │ (Local)  │ │ (Junior) │ │ (Distributed)    │ │    │
│  │  └──────────┘ └──────────┘ └──────────────────┘ │    │
│  └─────────────────────────────────────────────────┘    │
│       │             │                                    │
├───────┼─────────────┼────────────────────────────────────┤
│       ▼             ▼                                    │
│  ┌──────────┐ ┌──────────────────────────────────┐      │
│  │ YaCy     │ │        YaCy P2P Network          │      │
│  │ Server   │ │  (Senior/Principal Nodes)         │      │
│  │ (Local)  │ │  通过 DHT 分布式索引全球网页      │      │
│  └──────────┘ └──────────────────────────────────┘      │
└──────────────────────────────────────────────────────────┘
```

## Level 0 vs Level 2 对比

### Level 0 — HTTP 客户端

- **依赖**: 本地运行的 YaCy 服务器
- **通信方式**: HTTP REST API (GET/POST)
- **适用场景**: 有自己 YaCy 节点的用户、索引管理
- **API**: search, suggest, status, version, network, crawl_start, push_document, delete_index
- **模块**: `pyacy.client.YaCyClient`

### Level 2 — P2P 网络节点

- **依赖**: 仅 Python + 网络连接（无本地 YaCy）
- **通信方式**: P2P 协议（HTTP POST multipart + seed 字符串）
- **适用场景**: AI Agent、无 YaCy 服务器的用户、去中心化搜索
- **API**: bootstrap, search, hello_peer, ping_peers, get_peer_stats
- **模块**: `pyacy.network.PYaCyNode`, `pyacy.dht.search.DHTSearchClient`

## P2P 协议详解

### Seed 字符串格式

PYaCy 使用两种 seed 字符串格式:

**纯文本格式**（推荐，用于 P2P 通信）:
```
p|{Hash=abc123def456,Port=8090,PeerType=senior,IP=10.0.0.1,Name=my-node,LastSeen=20260428120000}
```

**压缩格式**（用于存储，不用于 P2P 通信，因为与 Java 不兼容）:
```
z|H4sIAAAAAAAA...
```

### Hello 协议握手流程

```
PYaCy (Junior)                          YaCy (Senior)
     │                                        │
     │  POST /yacy/hello.html                 │
     │  Content-Type: multipart/form-data     │
     │  ┌──────────────────────────────┐      │
     │  │ client=kN4l...               │      │
     │  │ key=kN4l...                  │      │
     │  │ seed=p|{Hash=...,PeerType=   │      │
     │  │     junior,...}              │      │
     │  └──────────────────────────────┘      │
     │ ──────────────────────────────────────>│
     │                                        │
     │  响应格式: key=value (每行一个)         │
     │  ┌──────────────────────────────┐      │
     │  │ ok 263                       │      │
     │  │ Name=remote-node             │      │
     │  │ Hash=def456...               │      │
     │  │ MyIP=119.78.253.19           │      │
     │  │ PeerType=junior              │      │
     │  │ seeds:1=p|{Hash=...,...}     │      │
     │  │ seeds:2=p|{Hash=...,...}     │      │
     │  └──────────────────────────────┘      │
     │ <──────────────────────────────────────│
```

### DHT 搜索请求格式

```
POST /yacy/search.html
Content-Type: multipart/form-data

Field              | Value
───────────────────|────────────────────
query              | 搜索词原文
ExclWords          | 排除词（空格分隔）
Enter              | Search
former             | 本地节点哈希
count              | 期望结果数
time               | 搜索时间限制（ms）
verify             | 结果验证方式
resource           | local/global
contentdom         | text/image/audio/video/app
nav                | 导航器类型
queryHash          | 词哈希列表（Base64，逗号分隔）
maximumRecords     | 最大记录数
urlmaskfilter      | URL 掩码过滤
prefermaskfilter   | 偏好掩码过滤
abstracts          | 是否请求摘要
```

## 词哈希算法

YaCy 使用自定义的 12 字符 Base64 哈希定位 DHT 中的词:

```python
from pyacy.utils import word_to_hash, words_to_hash_query

# 单个词哈希
hash_value = word_to_hash("python")       # 例如 "kB7f9mPq2xL4"

# 多词哈希查询（用于 AND 搜索）
query_hashes = words_to_hash_query(["python", "distributed", "search"])
# 例如 "kB7f9mPq2xL4,mN3s8tUv5wX7,yR2a5bC8dE1f"
```

## 数据模型速查

### YaCyClient 层（Level 0）

| 模型 | 关键属性 |
|------|----------|
| `SearchResponse` | query, items, total_results, total_pages |
| `SearchResult` | title, link, description, host, size, guid |
| `SuggestResponse` | suggestions (word, count) |
| `PeerStatus` | status, uptime_hours, memory_used_mb, index_size |
| `VersionInfo` | version, svn_revision, java_version, build_date |
| `NetworkInfo` | peer_name, peer_hash, active_peers, passive_peers |
| `PushResponse` | success, message, url_hash |

### P2P 层（Level 2）

| 模型 | 关键属性 |
|------|----------|
| `Seed` | name, hash, peer_type, ip, port, base_url |
| `HelloResult` | success, your_ip, your_type, seeds |
| `P2PResponse` | success, data, raw, status_code |
| `DHTSearchResult` | success, references, links, join_count |
| `DHTReference` | url_hash, title, url, description, ranking |

## 异常层次结构

```
PYaCyError (基类)
├── PYaCyConnectionError    — 网络连接失败
├── PYaCyTimeoutError       — 请求超时
├── PYaCyResponseError      — 非预期的 HTTP 响应
│   ├── PYaCyAuthError      — 认证失败 (401/403)
│   └── PYaCyServerError    — 服务端错误 (5xx)
├── PYaCyValidationError    — 参数校验失败
└── PYaCyP2PError           — P2P 协议错误
```

## 无公网 IP 模式细节

PYaCy 的核心设计目标之一是**无公网 IP 友好**。实现方式:

1. **节点类型**: PYaCy 始终创建 Junior 类型 Seed（`Seed.create_junior()`）
2. **Seed 无 IP 字段**: Junior seed 不包含 IP 信息，避免无效连接尝试
3. **代理搜索**: DHT 搜索通过已连接的 Senior/Principal 节点代理执行
4. **单向通信**: Junior 主动连接 Senior，不需要 Senior 能反向连接 Junior
5. **种子列表**: 通过 HTTP GET 获取（无需 P2P 认证），而非仅靠 Hello 握手

这使得 PYaCy 可以在 NAT 后、无端口映射、无公网 IP 的环境中正常工作。
