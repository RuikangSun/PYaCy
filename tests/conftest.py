# -*- coding: utf-8 -*-
"""PYaCy 测试配置与共享夹具。

本模块提供 pytest 测试用例的共享配置，包括：
- 模拟 YaCy 服务器的 HTTP mock fixtures
- 客户端实例的 fixture
- 测试数据的常量定义
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# 确保 src 目录在 Python 路径中
_SRC_DIR = str(Path(__file__).parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# ---------------------------------------------------------------------------
# 常量：测试用 URL
# ---------------------------------------------------------------------------
TEST_BASE_URL = "http://localhost:8090"

# ---------------------------------------------------------------------------
# 模拟响应数据
# ---------------------------------------------------------------------------


def make_mock_search_response(
    query: str = "test",
    total_results: int = 42,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """构建模拟的搜索 API 响应。

    Args:
        query: 搜索词。
        total_results: 总结果数。
        items: 搜索结果列表。

    Returns:
        符合 YaCy search.json 格式的字典。
    """
    if items is None:
        items = [
            {
                "title": "Test Result 1",
                "link": "http://example.com/1",
                "description": "This is a <b>test</b> result.",
                "pubDate": "Mon, 01 Jan 2024 00:00:00 +0000",
                "sizename": "1234 kbyte",
                "host": "example.com",
                "path": "/1",
                "file": "/1",
                "guid": "abc123",
            },
            {
                "title": "Test Result 2",
                "link": "http://example.com/2",
                "description": "Another <b>test</b> result.",
                "pubDate": "Tue, 02 Jan 2024 00:00:00 +0000",
                "sizename": "5678 kbyte",
                "host": "example.com",
                "path": "/2",
                "file": "/2",
                "guid": "def456",
            },
        ]
    return {
        "searchTerms": query,
        "channels": [
            {
                "totalResults": total_results,
                "startIndex": 0,
                "itemsPerPage": 10,
                "items": items,
                "topwords": [{"word": "python"}, {"word": "javascript"}],
            }
        ],
    }


def make_mock_suggest_response(
    queries: list[str] | None = None,
) -> list[dict[str, str]]:
    """构建模拟的搜索建议响应。

    Args:
        queries: 建议词列表。

    Returns:
        符合 YaCy suggest.json 格式的列表。
    """
    if queries is None:
        queries = ["python", "python tutorial", "python download"]
    return [{"suggestion": q} for q in queries]


def make_mock_status_response() -> dict[str, Any]:
    """构建模拟的节点状态响应。"""
    return {
        "status": "running",
        "uptime": 3600000,  # 1 小时 (毫秒)
        "totalMemory": 1073741824,  # 1 GB
        "freeMemory": 536870912,  # 512 MB
        "indexSize": 12345,
        "crawlsActive": 2,
    }


def make_mock_version_response() -> dict[str, Any]:
    """构建模拟的版本信息响应。"""
    return {
        "version": "1.93",
        "svnRevision": "12345",
        "buildDate": "2024-01-01",
        "javaVersion": "17.0.8",
    }


def make_mock_network_response() -> dict[str, Any]:
    """构建模拟的网络统计响应。"""
    return {
        "peers": {
            "your": {
                "name": "test-peer",
                "hash": "abc123hash",
            },
            "all": {
                "active": 150,
                "passive": 50,
                "potential": 200,
                "count": 123456789,
            },
        }
    }


def make_mock_push_response(success: bool = True) -> dict[str, Any]:
    """构建模拟的文档推送响应。"""
    return {
        "count": "1",
        "successall": "true" if success else "false",
        "item-0": {
            "item": "0",
            "url": "http://example.com/doc.html",
            "success": "true" if success else "false",
            "message": "ok" if success else "parsing error",
        },
        "countsuccess": 1 if success else 0,
        "countfail": 0 if success else 1,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """提供一个模拟的客户端实例（不实际连接）。"""
    from pyacy import YaCyClient
    return YaCyClient(base_url=TEST_BASE_URL)


@pytest.fixture
def mock_session() -> MagicMock:
    """提供一个模拟的 requests.Session。"""
    return MagicMock()


def mock_response(
    json_data: Any = None,
    status_code: int = 200,
    text: str = "",
    content: bytes = b"",
) -> MagicMock:
    """创建模拟的 requests.Response 对象。

    Args:
        json_data: 模拟的 JSON 响应数据。
        status_code: HTTP 状态码。
        text: 响应文本。
        content: 响应二进制内容。

    Returns:
        模拟的 Response 对象。
    """
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.content = content
    if json_data is not None:
        response.json.return_value = json_data
    else:
        response.json.return_value = {}
    return response
