# PYaCy — 智能体入口

> **PYaCy** 是 [YaCy](https://yacy.net/) 分布式搜索引擎的 Python 实现。它不仅封装了 YaCy REST API，还能直接参与 P2P 分布式网络 — 搜索、爬取、索引、RWI 拉取，**零第三方运行时依赖**。本文档面向 **AI 智能体**（Openclaw、OpenAkita等），在给人类阅读的文档基础上，描述如何使用 PYaCy 的 **Skills** 接入分布式搜索网络。
> 文档更新时间：2026-05-14

**版本**: 0.4.1
**许可证**: MIT
**仓库**: https://github.com/RuikangSun/PYaCy

---

## 1. 我是智能体，我为什么要用 PYaCy？

**核心价值**：不必依赖 Google/Bing 等单一搜索引擎，通过 P2P 网络自主搜索互联网。

| 我能做什么          | 一句话说明                                                          |
| ------------------- | ------------------------------------------------------------------- |
| DHT 分布式搜索      | 向 YaCy P2P 网络的多节点并行搜索，结果去重聚合                      |
| 高级搜索语法        | `site:` `filetype:` `intitle:` `inhtml:` `link:` 等操作符 |
| 网页爬取 + 本地索引 | 抓取指定 URL，存入 SQLite FTS5 全文索引                             |
| RWI Pull 模式       | 无需公网 IP，从 Senior 节点拉取反向词索引积累本地数据               |
| 状态监控            | 查看节点池规模、网络连接状态、RWI 统计                              |

---

## 2. 目录架构速览

```
PYaCy/
├── README_AGENT.md        # 你正在读的文档
├── README.md              # 给人类阅读的文档
├── skills/                # 智能体直接使用的技能
├── src/pyacy/             # 核心 Python 库
├── docs/                  # 开发文档
└── examples/              # 使用示例
```

---

## 3. Skills 使用指南

### 3.1 技能清单

请参考：skills/README.md

### 3.2 典型工作流

**场景 A：用户要求搜索网页**

```
1. 读取 skills/pyacy-status/SKILL.md → 检查节点状态
2. 如果未入网 → 读取 skills/pyacy-bootstrap/SKILL.md → 执行引导
3. 读取 skills/pyacy-search/SKILL.md → 执行 DHT 搜索
4. 返回结果给用户
```

**场景 B：用户要求搜索并积累本地索引**

```
1. 同场景 A 执行搜索
2. 读取 skills/pyacy-rwi/SKILL.md → 执行 pull_once() 拉取 RWI
3. 后续搜索自动合并本地 RWI + 远程 DHT 结果
```

**场景 C：用户要求抓取网页并索引**

```
1. 读取 skills/pyacy-crawler/SKILL.md → 使用 SimpleCrawler 抓取
2. 使用 LocalIndexer 索引到 SQLite FTS5
3. 用 indexer.search() 搜索本地索引
```

### 3.3 如何读取 SKILL.md

每个 `skills/*/SKILL.md` 文件包含：

```
---
name: 技能名称
description: >        ← 触发条件描述（什么时候用这个技能）
  关键词触发: ...
license: MIT
compatibility: >      ← 环境要求
  Python 3.10+, PYaCy>=0.4.0, ...
metadata:             ← 分类标签
---

# 技能标题

## 何时使用此技能     ← 判断是否应该使用此技能
## 前置条件            ← 需要满足的条件
## 核心工作流程        ← 分步骤的代码示例
## 常见错误与处理      ← 遇到错误时如何恢复
## 注意事项            ← 限制和边界条件
```

**智能体应该**：

1. 先看 `description` 中的关键词触发，判断是否匹配当前用户请求
2. 再看「何时使用此技能」确认不误判
3. 按「核心工作流程」的代码示例调用
4. 遇到错误查「常见错误与处理」表

### 3.4 核心 API 速查

所有技能底层使用这些 Python 类（来自 `src/pyacy/`）：

```python
from pyacy import PYaCyNode          # P2P 节点（bootstrap + search + pull）
from pyacy import PYaCyAdapter       # 统一接口（自动并行本地+远程）
from pyacy import YaCyClient         # HTTP 客户端（需本地 YaCy 服务器）
from pyacy.crawler import SimpleCrawler    # 内置爬虫
from pyacy.indexer import LocalIndexer    # 本地 SQLite 索引
from pyacy.rwi import RWIStorage, RWIPuller  # RWI 存储与 Pull
```

---

## 4. 安装与运行

### 安装

```bash
pip install -e .
# 或者直接用 PYTHONPATH
export PYTHONPATH="$PWD/src:$PYTHONPATH"
```

PYaCy **零运行时依赖**，仅需 Python >= 3.9 标准库。

### 最简示例（3 行代码）

```python
from pyacy import PYaCyNode
node = PYaCyNode(name="agent-node")
node.bootstrap()
results = node.search("python", count=10)
print(f"结果: {len(results.references)} 条")
node.close()
```

---

## 5. 网络要求

当前版本 PYaCy **仅支持 Junior 模式**，无公网 IP 的用户可直接使用，后续版本可能需要你拥有公网IP条件。

---

## 6. 常见问题

**Q: 搜索返回 0 条结果？**

1. 确认 `node.bootstrap()` 已成功执行
2. 检查 `node.get_peer_stats()` 中 Senior 节点数 > 0
3. 执行 `node.pull_once()` 积累本地 RWI 后再搜索
4. 尝试更通用的搜索词（如 "python" 而非长尾中文词）
5. 使用高级语法时，操作符是客户端侧过滤，先确认 DHT 返回了原始结果

**Q: 如何提升搜索命中率？**

1. 定期执行 `node.pull_once()` 积累本地 RWI
2. 使用 `PYaCyAdapter` 自动并行本地+远程搜索
3. 增加搜索节点数：`node.search("query", max_peers=20)`

---

## 7. 协助开发

欢迎智能体（和使用智能体的人类）一起协助开发PYaCy！
