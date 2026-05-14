# PYaCy

English | [中文](README.md) | [I, Robot](README_AGENT.md)

> README last updated: 2026-05-14

**PYaCy** is a Python client library for the [YaCy](https://yacy.net/) distributed search engine. It not only wraps the YaCy REST API but also directly participates in the P2P distributed network — search, crawl, index, pull RWI — with **zero third-party runtime dependencies**.

---

## Features

| Category | Feature | Description |
|:---|------|------|
| **Search** | HTTP + DHT distributed search | Local/global/advanced syntax (`site:` `filetype:` `intitle:` etc.) |
| **P2P Network** | Bootstrap + peer discovery | 31 hardcoded seeds, auto-discovers ~160 peers |
| **DHT Routing** | Word hash XOR distance routing | Iterative search expansion, precise responsible peer targeting |
| **Crawler** | Built-in web crawler | Pure stdlib, depth/domain limits, robots.txt compliance, per-domain rate limiting |
| **Local Index** | SQLite FTS5 full-text indexing | Crawl then index, Chinese CJK tokenization support |
| **RWI Pull** | Proactive RWI data pulling | No public IP needed, fetch reverse word indexes from Senior peers |
| **API Adapter** | Unified search interface | Local RWI + remote DHT parallel query, seamless fallback |
| **Zero Deps** | Pure Python standard library | `urllib` + `sqlite3` + `html.parser`, pip install and go |
| **Agent Skills** | AI agent integration | 5 Agent Skills, ready for Claude Code / Cursor |

---

## Quick Start

### Installation

```bash
pip install -e .
```

PYaCy has **zero runtime dependencies**, requiring only Python >= 3.9.

### P2P Node — Join the YaCy network directly

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="my-node")
node.bootstrap()                          # Bootstrap, discover ~160 peers

# DHT distributed search
results = node.search("python", count=10)
for ref in results.references:
    print(f"{ref.title} — {ref.url}")

# Advanced search syntax
results = node.search('site:github.com python async', count=10)
results = node.search('filetype:pdf machine learning', count=10)

node.close()
```

### Crawler + Local Index

```python
from pyacy.crawler import SimpleCrawler
from pyacy.indexer import LocalIndexer

crawler = SimpleCrawler()
indexer = LocalIndexer()

# Fetch a page
result = crawler.fetch("https://example.com")
print(f"Title: {result.title}, Text: {len(result.text)} chars")

# Index locally
indexer.add_document(url=result.url, title=result.title, content=result.text)

# Search the local index
hits = indexer.search("example")
for hit in hits:
    print(f"{hit['title']} — {hit['url']}")
```

### RWI Pull — Build local index without a public IP

```python
from pyacy import PYaCyNode

node = PYaCyNode(name="my-node")
node.bootstrap()

# Pull RWI data from Senior peers
imported = node.pull_once()
print(f"Imported {imported} RWI entries")

# Check local RWI stats
stats = node.get_rwi_stats()
print(f"Local RWI: {stats['total']} entries")

# Search automatically merges local RWI + remote DHT
results = node.search("python", use_local_rwi=True)
node.close()
```

### Unified API Adapter

```python
from pyacy import PYaCyAdapter

adapter = PYaCyAdapter()
adapter.bootstrap()

# Local RWI + remote DHT parallel search
results = adapter.search("python")
print(f"Local: {results['local_count']}, Remote: {results['remote_count']}")

# Network status
status = adapter.get_network_status()
print(f"Known peers: {status['peer_count']}")
```

---

## API Reference

### Top-Level Entry Points

| Class | Purpose |
|---|------|
| `YaCyClient` | HTTP client, connects to a running YaCy node |
| `PYaCyNode` | P2P node, directly joins the YaCy distributed network |
| `PYaCyAdapter` | Unified API interface, local + remote parallel search |

### Default Junior Node Mode

| Type | Description | Public IP |
|:---|------|:---:|
| **Junior** | Passive node, cannot receive incoming connections (**default**) | Not required |
| **Senior** | Active node, can receive incoming connections | Required |
| **Principal** | Core node, provides network infrastructure | Required |

### Module Index

| Module | Key Classes/Functions | Description |
|:---|------|------|
| `pyacy.client` | `YaCyClient` | HTTP search, status, crawler control, document push |
| `pyacy.network` | `PYaCyNode` | P2P node lifecycle, bootstrap, search routing |
| `pyacy.dht.search` | `DHTSearchClient` | DHT hash routing, XOR distance, parallel search |
| `pyacy.search.query_parser` | `SearchQuery` | Advanced search syntax (site/filetype/intitle etc.) |
| `pyacy.rwi.storage` | `RWIStorage` | SQLite FTS5 RWI storage engine |
| `pyacy.rwi.pull` | `RWIPuller` | Pull mode, proactive RWI fetching |
| `pyacy.crawler.basic` | `SimpleCrawler` | Pure stdlib web crawler |
| `pyacy.crawler.robots` | `RobotsCache` | robots.txt parsing and compliance |
| `pyacy.indexer.local` | `LocalIndexer` | SQLite FTS5 local full-text index |
| `pyacy.api.adapter` | `PYaCyAdapter` | Unified search interface |
| `pyacy.p2p.seed` | `Seed`, `SeedKeys` | Peer data model |
| `pyacy.p2p.protocol` | `P2PProtocol` | P2P protocol codec |
| `pyacy.p2p.hello` | `HelloClient` | Hello handshake protocol |
| `pyacy.p2p.seeds` | `HARDCODED_SEEDS` etc. | Seed management and three-layer discovery |
| `pyacy.exceptions` | `PYaCyError` etc. (7 types) | Exception hierarchy |
| `pyacy.utils` | `yacy_base64_encode` etc. | Base64, word hash, XOR distance |

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Run unit tests only
pytest tests/ -v --ignore=tests/test_live_network.py --ignore=tests/live_network_test.py

# Code formatting
black src/ tests/
ruff check src/ tests/
```

### Running Live P2P Tests

```bash
# Using default seed peers
python tests/test_live_network.py

# Using custom seeds (if your network is restricted)
python tests/test_live_network.py --seeds http://your-reachable-node:8090

# Conservative parameters (long timeout, long delay)
python tests/test_live_network.py --timeout 45 --delay 2.0
```

---

## Roadmap

### Completed

| Milestone | Version | Description |
|:---|:---|------|
| HTTP Client | v0.1.0 | Search, status, crawler, push, blacklist |
| Data Models + Exceptions | v0.1.0 | SearchResponse, PeerStatus etc. + 7 exception types |
| P2P Seed Model & Protocol | v0.2.0 | Seed codec, P2PProtocol, Hello handshake |
| DHT Distributed Search | v0.2.0 | Multi-peer parallel search, dedup & aggregation |
| Network Bootstrapping | v0.2.0 | Auto-bootstrap, peer discovery |
| Zero Dependencies | v0.2.4 | Removed requests, pure urllib |
| DHT Hash Routing | v0.3.0 | XOR distance routing, iterative expansion, 31 hardcoded seeds |
| Response Parsing Fixes | v0.3.1 | resourceN fields, SimpleCoding, backward compatibility |
| Chinese Compatibility | v0.3.2 | Chinese comma, case-insensitive fields, fallback, search cache |
| RWI Storage | v0.4.0 | SQLite FTS5 storage engine, TTL expiry |
| RWI Pull | v0.4.0 | Proactive RWI pulling (no public IP needed) |
| Crawler + Local Index | v0.4.1 | SimpleCrawler + LocalIndexer (SQLite FTS5) |
| Advanced Search Syntax | v0.4.1 | site:/filetype:/intitle:/inhtml: operators |
| robots.txt Compliance | v0.4.1 | RobotsCache, per-domain rate limiting |
| API Adapter | v0.4.1 | PYaCyAdapter unified search interface |
| Agent Skills | v0.4.1 | 5 skills (search/bootstrap/crawler/status/rwi) |

### In Progress / Planned

| Milestone | Description | Complexity |
|:---|------|:---:|
| Senior Node Mode | Port listening, incoming connections, DHT routing table, RWI distribution | ★★★★★ |
| GUI | Flet + pyecharts cross-platform GUI | ★★★★ |
| kelondro-Compatible Storage | Index format compatible with YaCy Java edition | ★★★★ |
| Web UI | Simple web management interface | ★★★ |

---

## Contributing

### Dev Environment Setup

```bash
git clone https://github.com/RuikangSun/PYaCy.git
cd PYaCy
pip install -e ".[dev]"
pytest tests/ -v  # ensure tests pass
```

### Code Style

- **Formatting**: [Black](https://github.com/psf/black) (line-length=120)
- **Linting**: [Ruff](https://github.com/astral-sh/ruff)
- **Type Checking**: [mypy](https://github.com/python/mypy)
- All public APIs require docstrings (Google style)
- New features must include unit tests

### Commit Guidelines

1. Update your progress in `dev/reports/ROADMAP.md`
2. Ensure `pytest tests/` all pass
3. Update `docs/` for new modules
4. Follow `__init__.py::__version__` for versioning

### Documentation Collaboration

See [dev/DEVELOPMENT_SPEC.md](dev/DEVELOPMENT_SPEC.md) for development specifications, including:
- Naming conventions
- Module responsibility boundaries
- New capability protocol
- Version changelog format

---

## License

MIT License — see [LICENSE](LICENSE).