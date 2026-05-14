# Agent 技能使用指南

PYaCy 提供了 5 个 Agent 技能（SKILL.md），供 AI 智能体接入 YaCy P2P 搜索网络。

## 技能清单

| 技能 | 触发场景 | 需要本地 YaCy | 公网 IP |
|------|----------|:---:|:---:|
| `pyacy-search` | "帮我搜索 XXX"、"查找关于 Y 的信息" | ❌ | ❌ |
| `pyacy-bootstrap` | "接入 YaCy 网络"、"连接 P2P 网络" | ❌ | ❌ |
| `pyacy-crawler` | "抓取这个网页并索引"、"爬取这个网站" | ❌ | ❌ |
| `pyacy-status` | "检查搜索节点状态"、"网络状况如何" | 部分 | ❌ |
| `pyacy-rwi` | "导入 RWI 数据"、"更新本地索引" | ❌ | ❌ |

## 典型工作流

```
收到搜索请求
    → pyacy-status 检查网络状态
    → pyacy-bootstrap 引导入网（如未入网）
    → pyacy-search 执行 DHT 搜索（支持高级语法）
    → pyacy-rwi 导入 RWI（可选，积累本地索引）
    → 返回结果
```

## 技能详解

### `pyacy-search` — DHT 分布式搜索

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="agent-search")
node.bootstrap()

# 基础搜索
results = node.search("ShanghaiTech University", count=10)

# 高级搜索语法（v0.4.1）
results = node.search("site:github.com python async", count=10)
results = node.search("filetype:pdf machine learning", count=10)
results = node.search('site:edu intitle:"deep learning"', count=10)
results = node.search("/language/zh 人工智能", count=10)
```

**v0.4.1 新增**：完整的 YaCy 高级搜索语法支持（site:/filetype:/intitle:/inhtml:/author:/language/:/http/https:/date::-word），在客户端侧过滤 DHT 搜索结果。

### `pyacy-bootstrap` — P2P 网络引导

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="agent-node")
node.bootstrap(timeout=120)

# 检查网络状态
stats = node.get_peer_stats()
print(f"已发现 {stats['total_peers']} 个节点，{stats['senior_peers']} 个 Senior")
```

**v0.4.1 更新**：优化种子探测参数（并发 20，超时 5s，筛选阈值：在线≥24h + 索引≥500）。

### `pyacy-crawler` — 网页抓取与本地索引

```python
from pyacy.crawler import SimpleCrawler
from pyacy.indexer import LocalIndexer

crawler = SimpleCrawler()
indexer = LocalIndexer()

# 单页抓取
result = crawler.fetch("https://example.com")

# 本地索引
indexer.add_document(url=result.url, title=result.title, content=result.text)

# 递归爬取（v0.4.1）
results = crawler.crawl(
    start_url="https://example.com",
    max_depth=2,
    max_pages=20,
    domain_limit="example.com",
)

# 批量索引
for r in results:
    indexer.add_document(url=r.url, title=r.title, content=r.text)

# 搜索本地索引
hits = indexer.search("example")
```

**v0.4.1 新增**：递归爬取（深度/域限制 + URL 过滤器）、robots.txt 遵从（RobotsCache）、按域名限速调度器、本地 SQLite FTS5 全文索引。

### `pyacy-status` — 节点状态与网络信息

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="agent-status")
node.bootstrap()

stats = node.get_peer_stats()
print(f"节点: {stats['total_peers']} 总, {stats['senior_peers']} Senior")
print(f"RWI: {stats.get('rwi_count', 0)} 条本地")
print(f"分布: {stats.get('type_distribution', {})}")

# 使用 PYaCyAdapter 获取统一网络状态
from pyacy import PYaCyAdapter
adapter = PYaCyAdapter()
adapter.bootstrap()
status = adapter.get_network_status()
```

### `pyacy-rwi` — RWI 存储与 Pull 模式

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="agent-rwi")
node.bootstrap()

# Pull RWI（v0.4.0）
imported = node.pull_once(peers=5, word_count=3)
print(f"导入 {imported} 条 RWI")

# RWI 统计
stats = node.get_rwi_stats()
print(f"本地 RWI: {stats['total']} 条")

# 搜索自动合并本地 RWI
results = node.search("python", use_local_rwi=True)
```

**v0.4.1 修复**：DHT 哈希路由替代随机选择，`_find_responsible_peers()` 按 XOR 距离精确定位负责节点，参数优化（DEFAULT_PULL_PEERS=5, timeout=8000ms）。

---

## 安装技能

```bash
# 在 PYaCy 仓库根目录
# 将 skills/ 目录中的技能复制到你的 Agent 技能目录
cp -r skills/pyacy-search ~/.openakita/skills/
cp -r skills/pyacy-bootstrap ~/.openakita/skills/
cp -r skills/pyacy-crawler ~/.openakita/skills/
cp -r skills/pyacy-status ~/.openakita/skills/
cp -r skills/pyacy-rwi ~/.openakita/skills/
```

---

## 技能版本记录

| 版本 | 变更 |
|------|------|
| v0.3.1 | 初始版本，4 个技能 |
| v0.4.0 | 新增 pyacy-rwi 技能；更新 pyacy-crawler 支持本地爬虫+索引；所有技能兼容性标注更新至 PYaCy>=0.4.0 |
| v0.4.1 | pyacy-search 新增高级搜索语法说明；pyacy-rwi 修复 DHT 哈希路由 + 参数优化；pyacy-bootstrap 更新种子探测参数；pyacy-crawler 新增递归爬取和robots.txt遵从 |

---

## 参考

- [Agent Skills 规范](https://agentskills.io/specification)
- [PYaCy 项目](https://github.com/RuikangSun/PYaCy/)
- [PYaCy 架构文档](architecture.md)
- [PYaCy API 参考](api_reference.md)
