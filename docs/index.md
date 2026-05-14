# PYaCy 文档

PYaCy — YaCy 分布式搜索引擎的纯 Python 客户端库。

---

## 文档导航

| 文档 | 说明 | 目标读者 |
|:---|------|:---|
| [快速开始](quickstart.md) | 安装、两种使用模式、高级搜索、爬虫+索引、API 适配器 | 新用户 |
| [架构说明](architecture.md) | 整体分层架构、数据流、设计决策 | 开发者 |
| [API 参考](api_reference.md) | 完整 API 文档（所有模块、类、方法） | 开发者 |
| [Agent 技能使用](agent_skills.md) | 5 个 Agent Skill 的安装与使用指南 | AI Agent 开发者 |

---

### 核心能力

- 🔍 **双重搜索**: HTTP 客户端 + P2P DHT 分布式搜索
- 🏷️ **高级搜索语法**: `site:` `filetype:` `intitle:` `inhtml:` `/language/` 等
- 🕷️ **内置爬虫**: 纯标准库网页抓取，支持递归、域限制、robots.txt 遵从
- 📇 **本地索引**: SQLite FTS5 全文索引，支持中文
- 📥 **RWI Pull**: 无需公网 IP，主动从 Senior 节点拉取反向索引
- 🔌 **统一适配器**: 本地 RWI + 远程 DHT 并行搜索，自动回退
- 📦 **零运行时依赖**: Python ≥ 3.9 标准库即用
- 🤖 **Agent Skills**: 5 个 AI 智能体技能

### 已验证

- ✅ 387 单元测试通过
- ✅ 搜索 "ShanghaiTech University" → 55 条引用
- ✅ Bootstrap 成功率 100%（~160 节点，159 Senior）

---

## 项目链接

- **GitHub**: [https://github.com/RuikangSun/PYaCy](https://github.com/RuikangSun/PYaCy)
- **License**: MIT
- **Python**: ≥ 3.9
