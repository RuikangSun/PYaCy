# Agent 技能使用指南

PYaCy 提供了 5 个 Agent 技能（SKILL.md），供 AI 智能体接入 YaCy P2P 搜索网络。

## 技能清单

| 技能 | 触发场景 | 需要本地 YaCy | 公网 IP |
|------|----------|:---:|:---:|
| `pyacy-search` | "帮我搜索 XXX" | ❌ | ❌ |
| `pyacy-bootstrap` | "接入 YaCy 网络" | ❌ | ❌ |
| `pyacy-crawler` | "抓取这个网页并索引" | ❌ | ❌ |
| `pyacy-status` | "检查搜索节点状态" | 部分 | ❌ |
| `pyacy-rwi` | "导入 RWI 数据" | ❌ | ❌ |

## 典型工作流

```
收到搜索请求
    → pyacy-status 检查状态
    → pyacy-bootstrap 引导入网（如未入网）
    → pyacy-search 搜索
    → pyacy-rwi 导入 RWI（可选，提升后续搜索质量）
```

## 安装技能

```bash
# 在 PYaCy 仓库根目录
# 将 skills/ 目录中的技能复制到你的 Agent 技能目录
cp -r skills/pyacy-search ~/.openakita/skills/
cp -r skills/pyacy-bootstrap ~/.openakita/skills/
# ... 其他技能
```

## v0.4.0 新增功能

- **RWI Pull**: 无需公网 IP，主动从 Senior 节点拉取 RWI 数据
- **本地索引**: 爬取的网页自动索引到本地 SQLite
- **统一搜索**: 本地 RWI + 远程 DHT 并行搜索
- **PYaCyAdapter**: 统一 API 接口，简化智能体调用

## 技能更新记录

| 版本 | 变更 |
|------|------|
| v0.3.1 | 初始版本，4 个技能 |
| v0.4.0 | 新增 pyacy-rwi 技能，更新所有技能兼容性标注 |
