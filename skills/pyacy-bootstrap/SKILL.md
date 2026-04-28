---
name: pyacy-bootstrap
description: >
  引导 PYaCy 节点接入 YaCy 分布式 P2P 搜索引擎网络。
  当需要将节点加入 P2P 网络、发现其他节点、建立 P2P 连接时使用此技能。
  Junior 节点无需公网 IP，通过 Public Seed 节点接入网络。
  关键词触发: bootstrap、入网、引导、发现节点、P2P连接、节点发现、peer discovery、网络接入。
license: MIT
compatibility: >
  Python 3.9+, PYaCy>=0.2.3, 网络连接（能访问至少一个 YaCy Public Seed 节点）。
  Junior 模式无需公网 IP。PYaCy 仓库: https://github.com/pyacy/pyacy
metadata:
  level: 2
  category: p2p
  requires_bootstrap: false
  network_access: true
---

# PYaCy Bootstrap — P2P 网络引导与节点发现

## 何时使用此技能

**必须使用本技能的场景**：
- 需要将 PYaCy 节点接入 YaCy P2P 网络
- 节点首次启动，需要发现网络中的其他节点
- 已知节点池为空或过期，需要刷新
- 用户说"接入 YaCy 网络"、"加入 P2P"、"Bootstrap"
- 执行搜索前需要确保节点已引导

**不需要本技能的场景**：
- 节点已引导且节点池充足（`node.is_bootstrapped == True` 且 `node.peer_count > 0`）
- 仅需要搜索 → 使用 `pyacy-search` 技能

## 前置条件

1. 已安装 PYaCy 包: `pip install pyacy`
2. 网络能访问至少一个 YaCy Public Seed 节点（默认使用 5 个公共种子）
3. 无需公网 IP（PYaCy 默认为 Junior 节点）

## 核心工作流程

### 步骤 1: 创建 PYaCy 节点

```python
from pyacy import PYaCyNode

# 创建 Junior 节点（无需公网 IP）
node = PYaCyNode(
    name="my-agent-node",    # 节点名称（可选，自动生成）
    port=8090,               # 本地端口标识（Junior 不绑定端口）
    timeout=30,              # P2P 请求默认超时（秒）
    network_name="freeworld", # YaCy 网络名称
)
print(f"节点哈希: {node.hash}")  # 12 字符 Base64 哈希
print(f"节点名称: {node.name}")
```

### 步骤 2: 执行网络引导

```python
success = node.bootstrap(
    max_peers=100,    # 最大发现节点数
    rounds=2,         # 发现轮数
)

if success:
    print(f"引导成功！发现 {node.peer_count} 个节点")
    print(f"其中 Senior/Principal: {node.senior_count}")
else:
    print("引导失败，检查网络连接或种子节点")
```

### 步骤 3: 检查引导结果

```python
# 查看节点统计
stats = node.get_peer_stats()
print(f"总节点数: {stats['total_peers']}")
print(f"Senior 节点数: {stats['senior_peers']}")
print(f"已引导: {stats['is_bootstrapped']}")
print(f"节点类型分布: {stats.get('type_distribution', {})}")

# 查看前 5 个已知节点
for hash_key, seed in list(node.peers.items())[:5]:
    print(f"  {seed.name} ({seed.peer_type}) — {seed.base_url}")
```

## 自定义种子节点

如果默认的公共种子不可达，可以指定自定义种子:

```python
custom_seeds = [
    "http://my-yacy-node.example.com:8090",
    "http://another-peer.local:8090",
]

node = PYaCyNode(
    name="custom-seed-node",
    seed_urls=custom_seeds,
)
node.bootstrap()
```

### 默认公共种子节点列表

PYaCy 内置了 5 个 YaCy freeworld 网络的公共种子:
1. `http://yacy.searchlab.eu:8090`
2. `http://yacy.dyndns.org:8090`
3. `http://130.255.73.69:8090`
4. `http://suen.ddns.net:8090`
5. `http://77.87.48.15:8090`

## 无公网 IP 的工作原理

PYaCy 专为无公网 IP 环境设计:

```
┌─────────────┐     seedlist.json      ┌──────────────────┐
│  PYaCy      │ ◄────────────────────  │  Public Seed     │
│  (Junior)   │     (HTTP GET)         │  (Senior/        │
│  无公网 IP  │                         │   Principal)     │
└──────┬──────┘                        └────────┬─────────┘
       │                                        │
       │  DHT 搜索请求                          │
       │  (HTTP POST,                            │
       │   Senior 代理)                          │
       ▼                                        ▼
  ┌─────────────────────────────────────────────────┐
  │              YaCy P2P 网络                       │
  │        (其他 Senior/Principal 节点)              │
  └─────────────────────────────────────────────────┘
```

1. Junior 节点通过 HTTP GET 从种子节点获取 `seedlist.json`（已知节点列表）
2. 种子列表包含网络中其他 Senior/Principal 节点的 IP、端口、哈希
3. Junior 将节点信息存入本地节点池
4. 搜索时，Junior 向池中的 Senior 节点发起 DHT 搜索请求（Senior 代理执行）

## 保活与维护

```python
# 向部分节点发送 Hello 保活
ping_results = node.ping_peers(max_peers=10)
for r in ping_results:
    print(f"  {r['peer']}: IP={r.get('your_ip', 'N/A')}")

# 手动对单个节点做 Hello
target = list(node.peers.values())[0]
result = node.hello_peer(target)
if result:
    print(f"Hello 成功: IP={result['your_ip']}, 类型={result['your_type']}")
```

## 节点类型说明

| 类型 | 英文 | 说明 |
|------|------|------|
| 处女 | Virgin | 从未接入网络的节点 |
| 初级 | Junior | 无公网端口的节点（PYaCy 默认角色） |
| 高级 | Senior | 有公网端口的节点，可代理搜索 |
| 主节点 | Principal | 网络中的稳定核心节点 |

## 常见错误与处理

| 错误 | 原因 | 处理 |
|------|------|------|
| 所有种子节点不可达 | 网络防火墙/代理限制 | 使用 `--seeds` 指定可访问的自定义种子 |
| Bootstrap 耗时过长 | 种子节点响应慢 | 减少 `max_peers` 或 `rounds` 参数 |
| 发现 0 个节点 | 种子节点返回空 seedlist | 检查种子节点是否运行最新版 YaCy |
| seedlist.json 返回空 | 节点配置问题或格式不兼容 | 检查种子 URL 是否以 `/` 结尾 |

## 注意事项

- **Bootstrap 是幂等操作**: 可多次调用，新发现的节点会追加到已知池
- **节点池持久化**: 当前版本节点池存于内存，节点重启后需重新 Bootstrap
- **速率限制**: 避免短时间内频繁 Hello，可能被对端限流（建议间隔 ≥ 1 秒）
- **网络状态**: P2P 节点状态不可控，部分节点离线属正常现象
