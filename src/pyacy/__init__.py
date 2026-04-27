# -*- coding: utf-8 -*-
"""PYaCy — YaCy 分布式搜索引擎的 Python 客户端库。

**PYaCy** 提供了与 YaCy 搜索节点通信的完整 Python 接口，
支持搜索查询、状态监控、爬虫控制和文档索引等核心功能。

快速开始::

    from pyacy import YaCyClient

    with YaCyClient("http://localhost:8090") as client:
        # 搜索
        results = client.search("python", resource="global")
        for item in results.items:
            print(f"{item.title} — {item.link}")

        # 状态查询
        status = client.status()
        print(f"索引文档数: {status.index_size}")

项目主页: https://github.com/pyacy/pyacy
"""

from .client import YaCyClient
from .exceptions import (
    PYaCyAuthError,
    PYaCyConnectionError,
    PYaCyError,
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

__all__ = [
    # 客户端
    "YaCyClient",
    # 异常
    "PYaCyError",
    "PYaCyConnectionError",
    "PYaCyTimeoutError",
    "PYaCyResponseError",
    "PYaCyAuthError",
    "PYaCyServerError",
    "PYaCyValidationError",
    # 模型
    "SearchResponse",
    "SearchResult",
    "SuggestResponse",
    "PeerStatus",
    "VersionInfo",
    "NetworkInfo",
    "PushResponse",
]

__version__ = "0.1.0"
