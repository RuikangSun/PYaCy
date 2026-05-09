# -*- coding: utf-8 -*-
"""PYaCy — YaCy 分布式搜索引擎的 Python 客户端库。

**PYaCy** 提供了与 YaCy 搜索节点通信的完整 Python 接口，
支持搜索查询、状态监控、爬虫控制、P2P 网络接入和 DHT 搜索等核心功能。

快速开始::

    # HTTP 客户端模式
    from pyacy import YaCyClient

    with YaCyClient("http://localhost:8090") as client:
        results = client.search("python", resource="global")
        for item in results.items:
            print(f"{item.title} — {item.link}")

    # P2P 网络模式
    from pyacy import PYaCyNode

    node = PYaCyNode(name="my-pyacy")
    node.bootstrap()
    for ref in node.search("hello world").references:
        print(ref.url)

项目主页: https://github.com/RuikangSun/PYaCy
许可证: MIT
"""

from .client import YaCyClient
from .exceptions import (
    PYaCyAuthError,
    PYaCyConnectionError,
    PYaCyError,
    PYaCyP2PError,
    PYaCyResponseError,
    PYaCyServerError,
    PYaCyTimeoutError,
    PYaCyValidationError,
)
from .models import (
    NetworkInfo,
    PeerStatus,
    PushResponse,
    SearchResponse,
    SearchResult,
    SuggestResponse,
    VersionInfo,
)
from .network import PYaCyNode
from .p2p import (
    Seed,
    SeedKeys,
    PEERTYPE_JUNIOR,
    PEERTYPE_SENIOR,
    PEERTYPE_PRINCIPAL,
    P2PProtocol,
    HelloClient,
)
from .dht import (
    DHTSearchClient,
    DHTSearchResult,
    DHTReference,
)
from .rwi import RWIStorage, RWIPuller, RWIEntry
from .crawler import SimpleCrawler, CrawlResult
from .indexer import LocalIndexer, IndexedDocument
from .api import PYaCyAdapter

__all__ = [
    # HTTP 客户端
    "YaCyClient",
    # P2P 网络
    "PYaCyNode",
    "P2PProtocol",
    "HelloClient",
    "Seed",
    "SeedKeys",
    "PEERTYPE_JUNIOR",
    "PEERTYPE_SENIOR",
    "PEERTYPE_PRINCIPAL",
    # DHT 搜索
    "DHTSearchClient",
    "DHTSearchResult",
    "DHTReference",
    # RWI 存储（v0.4.0 新增）
    "RWIStorage",
    "RWIPuller",
    "RWIEntry",
    # 爬虫（v0.4.0 新增）
    "SimpleCrawler",
    "CrawlResult",
    # 本地索引（v0.4.0 新增）
    "LocalIndexer",
    "IndexedDocument",
    # API 适配器（v0.4.0 新增）
    "PYaCyAdapter",
    # 异常
    "PYaCyError",
    "PYaCyConnectionError",
    "PYaCyTimeoutError",
    "PYaCyResponseError",
    "PYaCyAuthError",
    "PYaCyServerError",
    "PYaCyValidationError",
    "PYaCyP2PError",
    # 模型
    "SearchResponse",
    "SearchResult",
    "SuggestResponse",
    "PeerStatus",
    "VersionInfo",
    "NetworkInfo",
    "PushResponse",
]

__version__ = "0.4.0"
