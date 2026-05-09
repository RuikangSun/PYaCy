# 快速开始

## 安装

```bash
git clone https://github.com/RuikangSun/PYaCy.git
cd PYaCy
pip install -e .
```

PYaCy **零运行时依赖**，仅需 Python ≥ 3.10 标准库。

## 两种使用模式

### 模式 1：HTTP 客户端（连接已运行的 YaCy 节点）

```python
from pyacy import YaCyClient

with YaCyClient("http://yacy.searchlab.eu:8090") as client:
    # 搜索
    results = client.search("ShanghaiTech University", resource="global")
    for item in results.items:
        print(f"{item.title} — {item.link}")

    # 查看节点状态
    status = client.status()
    print(f"节点名: {status.name}, 索引数: {status.icount}")
```

### 模式 2：P2P 网络（直接接入 YaCy 分布式网络）

```python
from pyacy import PYaCyNode

# 创建节点并引导入网
node = PYaCyNode(name="my-pyacy")
node.bootstrap()  # 发现 ~160 个节点，约 30-60 秒

# DHT 分布式搜索
results = node.search("ShanghaiTech University", count=10)
for ref in results.references:
    print(f"{ref.title} — {ref.url}")

print(f"搜索耗时: {results.searchtime}ms, 参与节点: {results.peer_count}")
node.close()
```

## RWI 本地存储（v0.4.0）

```python
from pyacy import PYaCyNode
from pyacy.rwi import RWIStorage, RWIPuller

node = PYaCyNode(name="my-pyacy")
node.bootstrap()

# 启动 Pull 模式 — 主动从 Senior 节点拉取 RWI
imported = node.pull_once()
print(f"导入 {imported} 条 RWI")

# 查看本地 RWI 统计
stats = node.get_rwi_stats()
print(f"本地存储: {stats['total']} 条")

node.close()
```

## 本地网页索引（v0.4.0）

```python
from pyacy.crawler import SimpleCrawler
from pyacy.indexer import LocalIndexer

# 抓取网页
crawler = SimpleCrawler()
result = crawler.fetch("https://example.com")
print(f"标题: {result.title}, 文本长度: {len(result.text)}")

# 本地索引
indexer = LocalIndexer()
indexer.add_document(
    url=result.url,
    title=result.title,
    content=result.text,
)

# 搜索本地索引
hits = indexer.search("example")
for hit in hits:
    print(f"{hit.title} — {hit.url}")
```

## 统一 API 适配器（v0.4.0）

```python
from pyacy import PYaCyAdapter

adapter = PYaCyAdapter()
adapter.bootstrap()

# 本地 RWI + 远程 DHT 并行搜索
results = adapter.search("python")
print(f"本地命中: {results['local_count']}, 远程命中: {results['remote_count']}")

# 网络状态
status = adapter.get_network_status()
print(f"已知节点: {status['peer_count']}, RWI: {status['rwi_count']}")
```

## 无代码使用：示例脚本

```bash
# 基本 HTTP 搜索
python examples/basic_usage.py

# P2P 网络搜索
python examples/p2p_search.py
```
