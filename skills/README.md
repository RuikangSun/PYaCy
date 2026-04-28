# PYaCy Agent Skills

本目录包含 PYaCy 的 **Agent Skills**（智能体技能），遵循 [Agent Skills 规范](https://agentskills.io/specification)。

## 什么是 Agent Skills

Agent Skills 是供 AI 智能体（如 Claude Code、Cursor、其他 AI Agent 框架）自动发现和调用的能力模块。
每个技能以 `SKILL.md` 文件定义，包含 YAML 元数据（名称、描述、触发条件）和 Markdown 格式的操作指南。

**核心理念**: AI Agent 无需依赖单一搜索引擎（Google/Bing），通过 PYaCy 接入 YaCy P2P 分布式搜索网络，
自主查询互联网内容。

## 技能清单

| 技能 | 级别 | 说明 | 需要本地 YaCy |
|------|:----:|------|:-------------:|
| [pyacy-search](pyacy-search/SKILL.md) | Level 2 | DHT 分布式网页全文搜索 | ❌ |
| [pyacy-bootstrap](pyacy-bootstrap/SKILL.md) | Level 2 | P2P 网络引导与节点发现 | ❌ |
| [pyacy-crawler](pyacy-crawler/SKILL.md) | Level 0 | 网页抓取与索引管理 | ✅ |
| [pyacy-status](pyacy-status/SKILL.md) | Level 0+2 | 节点状态与网络信息查询 | 部分 |

## AI Agent 使用流程

典型的 AI Agent 搜索流程:

```
                  ┌──────────────┐
                  │  AI Agent    │
                  │  收到搜索请求 │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ 检查 PYaCy   │  ← pyacy-status 技能
                  │ 节点状态      │
                  └──────┬───────┘
                         │
                    ┌────┴────┐
                    │ 已引导？  │
                    └────┬────┘
                    否   │   是
                    ┌────▼───┐
                    │Bootstrap│  ← pyacy-bootstrap 技能
                    └────┬───┘
                         │
                         ▼
                  ┌──────────────┐
                  │  DHT 搜索    │  ← pyacy-search 技能
                  │  返回结果    │
                  └──────────────┘
```

## 技能文件格式

每个技能目录遵循以下结构:

```
skill-name/
├── SKILL.md          # 必需: YAML frontmatter + Markdown 指南
├── scripts/          # 可选: 可执行脚本
├── references/       # 可选: 参考文档（按需加载）
└── assets/           # 可选: 模板、图标等资源文件
```

SKILL.md 的 YAML frontmatter 示例:

```yaml
---
name: skill-name
description: >
  技能描述。包含何时使用此技能、触发关键词。
  AI Agent 根据此描述自动判断是否应激活该技能。
license: MIT
compatibility: Python 3.9+, PYaCy>=0.2.3
metadata:
  level: 2
  category: search
---
```

## 设计原则

1. **智能体友好**: 所有操作通过 Python API 完成，无需人工交互
2. **无公网 IP 优先**: 默认 Junior 模式，通过 Senior 节点代理
3. **渐进式加载**: SKILL.md 保持简洁（<500 行），详细参考放在 `references/`
4. **错误自愈**: 技能指南包含常见错误诊断与自动恢复流程
5. **MIT 协议**: 与 PYaCy 主项目一致，宽松开源

## 为 PYaCy 贡献技能

欢迎提交新的技能或改进现有技能！请遵循:

1. 阅读 [Agent Skills 最佳实践](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
2. 使用本目录中已有技能作为模板
3. SKILL.md 正文控制在 500 行以内
4. 包含完整的错误处理指南
5. 提供可验证的使用示例

## 参考

- [Agent Skills 规范](https://agentskills.io/specification)
- [Skill Creator 指南](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)
- [PYaCy 项目](https://github.com/pyacy/pyacy)
