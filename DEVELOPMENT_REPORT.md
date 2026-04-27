# PYaCy Level 0 开发报告

> **项目名称**: PYaCy — YaCy 分布式搜索引擎 Python 客户端
> **开发阶段**: Level 0（HTTP 客户端封装）
> **开发日期**: 2026-04-27
> **许可证**: MIT

---

## 一、项目概述

PYaCy Level 0 实现了与 YaCy 搜索节点通信的 HTTP 客户端库，
封装了搜索查询、节点状态监控、爬虫控制、文档索引等 10 个核心 API 端点，
提供类型安全的 Python 接口。全部代码基于 YaCy 公开 API 文档独立实现，
未引用 YaCy GPL 协议的 Java 源码。

## 二、代码统计

| 文件 | 行数 | 说明 |
|------|------|------|
| `src/pyacy/client.py` | 967 | YaCyClient HTTP 客户端核心 |
| `src/pyacy/exceptions.py` | 120 | 7 种自定义异常层次结构 |
| `src/pyacy/models.py` | 413 | 6 个数据模型类（含 from_json 工厂方法） |
| `src/pyacy/__init__.py` | 65 | 包入口，公共 API 导出 |
| `tests/conftest.py` | 207 | 测试夹具、模拟响应工厂函数 |
| `tests/test_client.py` | 775 | 73 个测试用例（10 个测试类） |
| `examples/basic_usage.py` | 126 | 完整的使用示例 |
| **合计** | **2,673** | |

## 三、已实现的 API 端点

| 端点 | 方法 | HTTP 方法 | 功能 |
|------|------|-----------|------|
| `/yacysearch.json` | `search()` | GET | 搜索查询（本地/P2P），支持分页、过滤、语言选择 |
| `/suggest.json` | `suggest()` | GET | 搜索建议（自动补全） |
| `/api/status_p.json` | `status()` | GET | 节点运行状态（状态、内存、索引大小） |
| `/api/version.json` | `version()` | GET | 版本信息（版本号、SVN 修订、Java 版本） |
| `/Network.json` | `network()` | GET | P2P 网络统计（活跃节点数、总 URL 数） |
| `/Crawler_p.html` | `crawl_start()` | POST | 启动爬虫任务 |
| `/CrawlStartExpert.html` | `crawl_start_expert()` | POST | 专家模式爬虫（更多控制选项） |
| `/api/push_p.json` | `push_document()` | POST | 推送文档到索引（支持元数据） |
| `/api/push_p.json` | `push_documents_batch()` | POST | 批量推送文档 |
| `/IndexDeletion_p.html` | `delete_index()` | POST | 删除索引文档（按 URL/主机/全量） |
| `/api/blacklists/*` | `get_blacklists()` 等 | GET | 黑名单管理（查看/获取/添加） |

## 四、架构设计

### 4.1 异常层次结构

```
PYaCyError                  (基类)
├── PYaCyConnectionError    (网络连接失败)
├── PYaCyTimeoutError       (请求超时)
├── PYaCyResponseError      (API 返回错误)
│   ├── PYaCyAuthError      (认证失败 401/403)
│   └── PYaCyServerError    (服务端内部错误 5xx)
└── PYaCyValidationError    (参数校验失败)
```

设计原则：
- **高内聚映射**: 每个 HTTP 错误类型映射到专用异常，调用方可精确捕获
- **保留原始信息**: 异常对象保存 status_code、response_body、原始异常等调试上下文
- **继承链合理**: `PYaCyAuthError → PYaCyResponseError → PYaCyError`，支持分级捕获

### 4.2 数据模型

所有 API 响应均返回类型安全的数据类（`@dataclass`），每个模型提供 `from_json()` 工厂方法和计算属性：

- **SearchResponse** / **SearchResult**: 搜索结果，含 `total_pages` 分页属性
- **SuggestResponse** / **SuggestResult**: 搜索建议
- **PeerStatus**: 节点状态，含 `memory_used_mb` / `uptime_hours` 计算属性
- **VersionInfo**: 版本信息
- **NetworkInfo**: P2P 网络统计
- **PushResponse** / **PushResult**: 文档推送结果

### 4.3 客户端关键特性

1. **自动重试**: 对 429/5xx 状态码使用指数退避自动重试（默认 3 次）
2. **上下文管理器**: 支持 `with YaCyClient(...) as client:` 自动清理连接
3. **参数预校验**: 搜索词、URL 等关键参数在发送前校验，避免无效请求
4. **超时控制**: 全局超时 + 单次请求超时双层控制
5. **None 参数清理**: 自动过滤 None 值参数，避免传递空查询参数

## 五、测试结果

```
✅ 73 passed in 0.15s

测试类覆盖：
├── TestClientInit (7)          客户端初始化与参数校验
├── TestInternalMethods (5)     内部工具方法
├── TestSearchAPI (8)           搜索/建议 API
├── TestStatusAPI (4)           状态/版本/网络 API
├── TestCrawlerAPI (4)          爬虫控制 API
├── TestPushAPI (7)             文档推送 API
├── TestIndexManagement (7)     索引管理与黑名单
├── TestErrorHandling (11)      错误处理与重试
├── TestPing (2)                Ping 连通性检查
├── TestDataModels (7)          数据模型构造与转换
└── TestEdgeCases (4)           边界情况
```

所有测试使用 `unittest.mock` 模拟 HTTP 请求，**不需要实际运行 YaCy 实例即可执行**。

## 六、技术决策记录

### 6.1 使用 requests 库而非 httpx
- **决策**: 使用 `requests`（同步 HTTP 客户端）
- **原因**: Level 0 阶段优先保证兼容性和稳定性。`requests` 生态成熟、
  错误处理完善、SSL 处理可靠。后续可按需添加 `httpx` 异步支持。

### 6.2 数据模型使用 dataclass 而非 pydantic
- **决策**: 使用标准库 `dataclasses.dataclass`
- **原因**: Level 0 不需要复杂的数据校验，`dataclass` 零依赖、轻量、
  Python 3.9+ 原生支持。后续需要严格校验时可迁移到 pydantic。

### 6.3 不依赖 YaCy GPL 代码
- **决策**: 所有代码基于 YaCy 公开 API 文档（wiki.yacy.net）独立实现
- **原因**: YaCy 使用 GPL 协议，PYaCy 使用 MIT 协议。
  直接参考 API 参数和响应格式，不复制 Java 实现代码。

### 6.4 中文注释 + Google 注释规范
- **决策**: 所有公开 API 使用 Google 风格的 Python docstring，
  注释使用中文编写
- **原因**: 满足用户明确要求的中文注释规范

## 七、已知限制

1. **仅支持 JSON 响应格式**: 部分 API 端点（如 status_p、crawler）同时支持
   XML/JSON，当前仅实现了 JSON 解析。未来可添加 XML 支持。

2. **无异步支持**: 当前为同步 HTTP 客户端。高并发场景需要异步版本。

3. **依赖 requests 库**: 未使用 Python 标准库 `urllib`，有外部依赖。

4. **缺少类型存根 (.pyi)**: 代码已全面使用类型注解，但未生成独立的 `.pyi` 文件。

5. **未完整实现 Solr API**: `/solr/select` 的高级查询功能暂未封装。

## 八、下一步计划（Level 1 预研）

Level 1 将在 Level 0 基础上增加：

1. **CLI 工具**: 基于 click/typer 的命令行界面
2. **异步客户端**: 基于 httpx/aiohttp 的异步版本
3. **配置管理**: 多节点管理、连接池
4. **缓存层**: 搜索结果缓存（减少重复请求）
5. **重试策略增强**: 更细粒度的重试配置
6. **XML 响应解析**: 支持所有 API 端点的 XML 格式

---

*报告生成时间: 2026-04-27 16:00 CST*
