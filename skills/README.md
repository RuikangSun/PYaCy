# PYaCy Agent Skills

本目录包含 PYaCy 的 **Agent Skills**（智能体技能），遵循 [Agent Skills 规范](https://agentskills.io/specification)。

## 什么是 Agent Skills

Agent Skills 是供 AI 智能体（如 Claude Code、Cursor、其他 AI Agent 框架）自动发现和调用的能力模块。
每个技能以 `SKILL.md` 文件定义，包含 YAML 元数据（名称、描述、触发条件）和 Markdown 格式的操作指南。

**核心理念**: AI Agent 无需依赖单一搜索引擎（Google/Bing），通过 PYaCy 接入 YaCy P2P 分布式搜索网络，
自主查询互联网内容。

## 技能清单

| 技能 | 模式 | 说明 | 需要本地 YaCy |
|------|:----:|------|:-------------:|
| [pyacy-search](pyacy-search/SKILL.md) | P2P | DHT 分布式网页全文搜索 | ❌ |
| [pyacy-bootstrap](pyacy-bootstrap/SKILL.md) | P2P | P2P 网络引导与节点发现 | ❌ |
| [pyacy-crawler](pyacy-crawler/SKILL.md) | HTTP+本地 | 网页抓取与本地索引管理 | 部分 |
| [pyacy-status](pyacy-status/SKILL.md) | HTTP+P2P | 节点状态与网络信息查询 | 部分 |
| [pyacy-rwi](pyacy-rwi/SKILL.md) | P2P | RWI 存储与 Pull 模式 | ❌ |

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
                  │ Pull RWI     │  ← pyacy-rwi 技能（可选，提升搜索质量）
                  │ 积累本地索引  │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │  DHT 搜索    │  ← pyacy-search 技能
                  │  + 本地 RWI  │
                  │  返回结果    │
                  └──────────────┘
```

## 技能版本记录

| 版本 | 变更 |
|------|------|
| v0.3.1 | 初始版本：pyacy-search, pyacy-bootstrap, pyacy-crawler, pyacy-status |
| v0.4.0 | 新增 pyacy-rwi；更新 pyacy-crawler 支持本地爬虫+索引；所有技能兼容性标注更新至 PYaCy>=0.4.0 |

## 技能文件格式

每个技能目录遵循以下结构:

```
skill-name/
├── SKILL.md          # 必需: YAML frontmatter + Markdown 指南
├── scripts/          # 可选: 可执行脚本
├── references/       # 可选: 参考文档（按需加载）
└── assets/           # 可选: 模板、图标等资源文件
```

## 设计原则

1. **智能体友好**: 所有操作通过 Python API 完成，无需人工交互
2. **无公网 IP 优先**: 默认 Junior 模式，通过 Senior 节点代理
3. **渐进式加载**: SKILL.md 保持简洁（<500 行），详细参考放在 `references/`
4. **错误自愈**: 技能指南包含常见错误诊断与自动恢复流程
5. **MIT 协议**: 与 PYaCy 主项目一致，宽松开源

## 参考

- [Agent Skills 规范](https://agentskills.io/specification)
- [PYaCy 项目](https://github.com/RuikangSun/PYaCy/)
- [PYaCy 文档](https://github.com/RuikangSun/PYaCy/tree/main/docs)
