# PYaCy

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-green)](https://github.com/RuikangSun/PYaCy)

English | [中文](README.md)

**PYaCy** is a Python client library for the [YaCy](https://yacy.net/) distributed search engine. It provides search queries, status monitoring, crawler control, P2P network bootstrapping, and DHT distributed search — all with **zero third-party runtime dependencies** (pure Python standard library).

## Features

- 🔍 **Search Queries** — Local and P2P global search
- 🌐 **P2P Network Bootstrapping** — Automatic node discovery from seed nodes
- 🤝 **Hello Handshake** — Exchange status information with other YaCy peers
- 📡 **DHT Distributed Search** — Cross-node distributed hash table queries
- 🕷️ **Crawler Control** — Start and manage web crawl jobs
- 📄 **Document Push** — Push documents directly into the YaCy index
- 🛡️ **Junior-Friendly** — Participate in the P2P network without a public IP
- 📦 **Zero Dependencies** — Pure `urllib` implementation, no third-party packages

## Quick Start

### Installation

```bash
pip install -e .
```

### Search & Status

```python
from pyacy import YaCyClient

with YaCyClient("http://localhost:8090") as client:
    # Search
    results = client.search("python", resource="global")
    for item in results.items:
        print(f"{item.title} — {item.link}")

    # Node status
    status = client.status()
    print(f"Index: {status.index_size} docs, uptime {status.uptime_hours:.1f}h")
```

### P2P Network & Distributed Search

```python
from pyacy import PYaCyNode

# Create a Junior node (no public IP required)
node = PYaCyNode(name="my-pyacy-node")
print(f"Node hash: {node.hash}")

# Bootstrap from public seed nodes
node.bootstrap()

# View network stats
stats = node.get_peer_stats()
print(f"Discovered {stats['total_peers']} peers")

# DHT distributed search
results = node.search("open source")
for ref in results.references:
    print(ref.url)

node.close()
```

## API Reference

### HTTP Client (`YaCyClient`)

| API Endpoint | Method | Description |
|--------------|--------|-------------|
| `/yacysearch.json` | `search()` | Search queries (local/P2P) |
| `/suggest.json` | `suggest()` | Search suggestions (autocomplete) |
| `/api/status_p.json` | `status()` | Node runtime status |
| `/api/version.json` | `version()` | Version information |
| `/Network.json` | `network()` | P2P network statistics |
| `/Crawler_p.html` | `crawl_start()` | Start a crawl job |
| `/CrawlStartExpert.html` | `crawl_start_expert()` | Expert-mode crawl start |
| `/api/push_p.json` | `push_document()` | Push document to index |
| `/IndexDeletion_p.html` | `delete_index()` | Delete index documents |
| `/api/blacklists/*` | `get_blacklists()` etc. | Blacklist management |

### P2P Network (`PYaCyNode`)

| Module | Class/Method | Description |
|--------|--------------|-------------|
| `pyacy.network` | `PYaCyNode` | P2P node management & network topology |
| `pyacy.p2p.seed` | `Seed` | Peer information model & serialization |
| `pyacy.p2p.protocol` | `P2PProtocol` | P2P protocol encoding/decoding |
| `pyacy.p2p.hello` | `HelloClient` | Hello handshake protocol |
| `pyacy.dht.search` | `DHTSearchClient` | DHT distributed search |

### Peer Types

| Type | Description | Public IP |
|------|-------------|:---------:|
| **Junior** | Passive peer, cannot accept incoming connections | ❌ Not required |
| **Senior** | Active peer, can accept incoming connections | ✅ Required |
| **Principal** | Core peer, provides network infrastructure | ✅ Required |

PYaCy runs as a **Junior** peer by default.

## Project Structure

```
PYaCy/
├── src/pyacy/
│   ├── __init__.py          # Package entry, public API exports
│   ├── client.py            # YaCyClient HTTP client
│   ├── exceptions.py        # Custom exception hierarchy
│   ├── models.py            # Data models (SearchResponse, etc.)
│   ├── utils.py             # Utilities (Base64, hashing, seed parsing)
│   ├── p2p/
│   │   ├── seed.py          # Seed data model
│   │   ├── protocol.py      # P2P protocol layer
│   │   └── hello.py         # Hello protocol client
│   ├── dht/
│   │   └── search.py        # DHT search client
│   └── network.py           # PYaCyNode network manager
├── tests/                   # Test suite (340 tests)
├── examples/                # Usage examples
├── skills/                  # Agent Skills (AI assistant integration)
├── pyproject.toml
└── LICENSE                  # MIT License
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run examples
python examples/basic_usage.py
python examples/p2p_search.py
```

## Roadmap

### ✅ Completed

| Milestone | Version | Description |
|-----------|---------|-------------|
| HTTP Client | v0.1.0 | YaCy REST API wrapper: search, status, crawler, push, blacklists |
| Data Models | v0.1.0 | Type-safe response parsing (SearchResponse, PeerStatus, etc.) |
| Exception Hierarchy | v0.1.0 | 7 custom exceptions covering connection/timeout/auth/response errors |
| P2P Seed Model | v0.2.0 | Seed data model, YaCy Base64 codec, seed string parsing |
| P2P Protocol Layer | v0.2.0 | P2PProtocol encoding/decoding, Hello handshake client |
| DHT Distributed Search | v0.2.0 | Multi-node parallel search, result deduplication & aggregation |
| Network Bootstrapping | v0.2.0 | Auto-bootstrap from public seed nodes, peer discovery |
| Junior Node Support | v0.2.2 | Full P2P functionality without a public IP |
| Hello Handshake Fix | v0.2.3 | Uncompressed seed format compatibility, 100% handshake success |
| Zero Dependencies | v0.2.4 | Removed `requests`, pure `urllib` standard library implementation |

### 🚧 In Progress

| Milestone | Description |
|-----------|-------------|
| Documentation | API docs, architecture guide, contribution guidelines |

### 📋 Planned

| Milestone | Description | Complexity |
|-----------|-------------|:----------:|
| RWI Index Receiving | Receive and store RWI references distributed by other peers | ★★★ |
| kelondro-Compatible Storage | Index storage format compatible with YaCy Java edition | ★★★★ |
| RWI Distribution Engine | Distribute local RWI references to other peers (requires public IP) | ★★★★ |
| Built-in Crawler | Standalone web crawler for building local Solr index | ★★★★ |
| Full P2P Node | Senior/Principal mode with incoming connection support | ★★★★★ |
| Web UI | Simple web management interface | ★★★ |

## License

MIT License — see [LICENSE](LICENSE).