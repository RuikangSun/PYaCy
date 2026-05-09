---
name: pyacy-bootstrap
description: >
  引导 PYaCy 节点接入 YaCy 分布式 P2P 搜索引擎网络。
  当需要将节点加入 P2P 网络、发现其他节点、建立 P2P 连接时使用此技能。
  Junior 节点无需公网 IP，通过 Public Seed 节点接入网络。
  v0.4.0 改进: 三层种子冗余（硬编码 + 缓存 + 在线），并行连通性探测。
  关键词触发: bootstrap、入网、引导、发现节点、P2P连接、节点发现、peer discovery、网络接入。
license: MIT
compatibility: >
  Python 3.10+, PYaCy>=0.4.0, 网络连接（能访问至少一个 YaCy Public Seed 节点）。
  Junior 模式无需公网 IP。PYaCy 仓库: https://github.com/RuikangSun/PYaCy
metadata:
  level: 2
  category: p2p
  requires_bootstrap: false
  network_access: true
---

# PYaCy Bootstrap — P2P 网络引导与节点发现

## 何时使用此技能

**必须使用此技能的场景**：
- 需要将 PYaCy 节点接入 YaCy P2P 网络
- 节点首次启动，需要发现网络中的其他节点
- 已知节点池为空或过期，需要刷新

**不需要本技能的场景**：
- 节点已引导且节点池充足（`node.is_bootstrapped == True`）
- 仅需要搜索 → 使用 `pyacy-search` 技能

## 前置条件

1. 已安装 PYaCy 包: `pip install pyacy`
2. 网络能访问至少一个 YaCy Public Seed 节点
3. 无需公网 IP（PYaCy 默认为 Junior 节点）

## 核心工作流程

### 步骤 1: 创建 PYaCy 节点

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="my-agent-node", port=8090)
print(f"节点哈希: {node.hash}")
```

### 步骤 2: 执行网络引导

```python
success = node.bootstrap(timeout=120)
if success:
    print(f"引导成功！发现 {node.peer_count} 个节点，其中 Senior: {node.senior_count}")
else:
    print("引导失败，检查网络连接")
```

### 步骤 3: 检查引导结果

```python
stats = node.get_peer_stats()
print(f"总节点数: {stats['total_peers']}")
print(f"Senior 节点数: {stats['senior_peers']}")
print(f"节点类型分布: {stats.get('type_distribution', {})}")
```

## 三层种子来源

v0.4.0 的 Bootstrap 使用三层冗余种子来源：

1. **本地缓存** `~/.pyacy/seed_cache.json`（上次发现的稳健节点）
2. **硬编码种子** 30 个精选节点（内置在 PYaCy 包中）
3. **在线种子** 从 seedlist.json 动态获取

启动时并行探测所有种子的连通性（5s 超时，20 并发），筛选 Senior/Principal 节点。

## 自定义种子节点

```python
node = PYaCyNode(
    name="custom-seed-node",
    seed_urls=["http://my-yacy-node.example.com:8090"],
)
node.bootstrap()
```

## 常见错误与处理

| 错误 | 原因 | 处理 |
|------|------|------|
| 所有种子节点不可达 | 网络防火墙/代理限制 | 使用 `seed_urls` 指定可访问的自定义种子 |
| Bootstrap 耗时过长 | 种子节点响应慢 | 正常现象，约 30-60 秒 |
| 发现 0 个节点 | 种子节点返回空 seedlist | 检查种子节点是否在线 |

## 注意事项

- **Bootstrap 是幂等操作**: 可多次调用，新发现的节点会追加到已知池
- **节点池内存存储**: 节点重启后需重新 Bootstrap
- **速率限制**: 避免短时间内频繁 Hello，建议间隔 ≥ 1 秒
