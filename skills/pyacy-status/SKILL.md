---
name: pyacy-status
description: >
  检查 PYaCy/YaCy 节点的运行状态、版本信息、P2P 网络连接情况和节点统计。
  当需要确认节点是否正常运行、查看索引大小、检查 P2P 连接状态时使用。
  关键词触发: 状态、版本、节点信息、网络统计、运行状态、status、version、network stats。
license: MIT
compatibility: >
  Python 3.9+, PYaCy>=0.2.3。YaCy 状态 API 需要本地或可访问的 YaCy 服务。
  P2P 节点状态无需本地 YaCy。PYaCy 仓库: https://github.com/pyacy/pyacy
metadata:
  level: 0
  category: status
  requires_bootstrap: false
  network_access: optional
---

# PYaCy 状态 — 节点状态与网络信息查询

## 何时使用此技能

**必须使用本技能的场景**：
- 检查 YaCy 服务是否正常运行
- 查看节点索引大小、内存使用、运行时间
- 获取 YaCy 版本信息
- 查看 P2P 网络统计（活跃节点数、URL 总数等）
- 确认 PYaCy P2P 节点的连接状态和节点池
- AI Agent 需要确认搜索基础设施健康状态

**不需要本技能的场景**：
- 执行搜索 → 使用 `pyacy-search` 技能
- 连接网络 → 使用 `pyacy-bootstrap` 技能

## 两大类状态查询

PYaCy 支持两种级别的状态查询:

| 级别 | 所需环境 | 查询能力 |
|------|----------|----------|
| **YaCy 服务状态** (Level 0) | 本地 YaCy 服务器 | 运行状态、内存、索引、版本、网络统计 |
| **PYaCy P2P 状态** (Level 2) | 无（纯 P2P 节点） | 节点池规模、连接状态、引导信息 |

## YaCy 服务状态（Level 0，需本地 YaCy）

### 检查节点运行状态

```python
from pyacy import YaCyClient

with YaCyClient("http://localhost:8090") as client:
    status = client.status()

    # 核心指标
    print(f"运行状态: {status.status}")           # online/offline
    print(f"运行时间: {status.uptime_hours:.1f} 小时")
    print(f"内存使用: {status.memory_used_mb:.0f} MB")
    print(f"内存空闲: {status.memory_free_mb:.0f} MB")
    print(f"索引大小: {status.index_size} 条文档")
    print(f"本地 URL: {status.local_url_count}")
    print(f"远程 URL: {status.remote_url_count}")
```

### 获取版本信息

```python
with YaCyClient("http://localhost:8090") as client:
    version = client.version()

    print(f"YaCy 版本: {version.version}")
    print(f"SVN 版本: r{version.svn_revision}")
    print(f"Java 版本: {version.java_version}")
    print(f"构建日期: {version.build_date}")
```

### 查看 P2P 网络统计

```python
with YaCyClient("http://localhost:8090") as client:
    network = client.network()

    print(f"节点名称: {network.peer_name}")
    print(f"节点哈希: {network.peer_hash}")
    print(f"活跃 Senior: {network.active_peers}")
    print(f"被动 Senior: {network.passive_peers}")
    print(f"潜在节点: {network.potential_peers}")
    print(f"总 URL 数: {network.total_urls:,}")
    print(f"网络类型: {network.network_type}")
```

### 快速连通性检查

```python
with YaCyClient("http://localhost:8090") as client:
    if client.ping():
        print("✅ YaCy 服务可访问")
    else:
        print("❌ YaCy 服务不可达")
```

## PYaCy P2P 节点状态（Level 2，纯 P2P）

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="status-check")

# 即使未引导也可查看基本信息
print(f"节点名称: {node.name}")
print(f"节点哈希: {node.hash}")
print(f"本地 Seed: {node.my_seed.name} ({node.my_seed.peer_type})")

# Bootstrap 后查看网络状态
node.bootstrap()
stats = node.get_peer_stats()

print(f"总节点数: {stats['total_peers']}")
print(f"Senior/Principal: {stats['senior_peers']}")
print(f"已引导: {stats['is_bootstrapped']}")
print(f"引导后时长: {node.bootstrap_age:.0f} 秒")
print(f"节点类型分布: {stats.get('type_distribution', {})}")
```

## 健康检查完整示例

以下是一个完整的健康检查函数，可嵌入 AI Agent 流程:

```python
from pyacy import YaCyClient, PYaCyNode
from pyacy.exceptions import PYaCyError


def health_check() -> dict:
    """执行完整的健康检查，返回状态报告。"""
    report = {
        "yacy_server": False,
        "yacy_version": None,
        "p2p_network": False,
        "peer_count": 0,
        "senior_count": 0,
        "index_size": 0,
        "errors": [],
    }

    # 检查本地 YaCy 服务
    try:
        client = YaCyClient("http://localhost:8090", timeout=5)
        if client.ping():
            report["yacy_server"] = True
            version = client.version()
            report["yacy_version"] = version.version
            status = client.status()
            report["index_size"] = status.index_size
        client.close()
    except PYaCyError as e:
        report["errors"].append(f"YaCy 服务: {e}")

    # 检查 P2P 网络
    try:
        node = PYaCyNode(name="health-check")
        if node.bootstrap(max_peers=50, rounds=1):
            report["p2p_network"] = True
            report["peer_count"] = node.peer_count
            report["senior_count"] = node.senior_count
        node.close()
    except Exception as e:
        report["errors"].append(f"P2P 网络: {e}")

    return report


# 使用
if __name__ == "__main__":
    import json
    print(json.dumps(health_check(), indent=2, ensure_ascii=False))
```

## 状态指标解读

| 指标 | 健康值 | 需关注 | 说明 |
|------|--------|--------|------|
| `status.status` | "online" | 非 "online" | 节点运行状态 |
| `uptime_hours` | > 0 | — | 运行时长 |
| `memory_used_mb` | < 服务器 80% | > 80% | 内存压力 |
| `index_size` | > 0 | 0 | 本地索引是否为空 |
| `senior_count` | > 0 | 0 | 无可用的 Senior 代理节点 |
| `peer_count` | > 10 | < 5 | P2P 节点池是否充足 |
| `is_bootstrapped` | True | False | 是否已接入网络 |

## 常见错误与处理

| 错误 | 原因 | 处理 |
|------|------|------|
| `PYaCyConnectionError` | YaCy 未启动 | 启动 YaCy 服务 |
| `version` 和 `status` 返回空 | API 路径变化 | 检查 YaCy 版本是否 ≥ 1.92 |
| `network()` 返回数据异常 | 网络功能未启用 | 在 YaCy 设置中启用 P2P |
| `ping()` 返回 False | 端口错误或防火墙 | 检查 8090 端口是否监听 |
| Bootstrap 后 peer_count=0 | 种子节点不可达 | 使用 `--seeds` 指定自定义种子 |

## 注意事项

- **ping() 是轻量检查**: 只做 HTTP HEAD 请求，适合频繁调用
- **status() 可能需认证**: 部分 YaCy 配置限制 `/api/status_p.json` 访问
- **节点池信息存于内存**: PYaCy 进程重启后节点池清空，需重新 Bootstrap
- **网络状态不稳定**: P2P 网络中节点状态动态变化，属正常现象
