# -*- coding: utf-8 -*-
"""PYaCy 本地索引模块。

本模块提供了基于 SQLite FTS5 的本地全文索引功能，
用于存储和检索爬取的网页内容。

设计原则:
    - 零外部依赖（SQLite FTS5 内置于 Python 标准库）
    - unicode61 分词器自动处理中文字符
    - 支持 Agent 友好的元数据标签
    - 与 RWI 存储共享数据库连接

使用示例::

    from pyacy.indexer import LocalIndexer

    indexer = LocalIndexer("~/.pyacy/index.db")
    indexer.add_document(
        url="https://example.com",
        title="示例页面",
        content="这是页面内容...",
        tags=["example", "demo"],
    )
    results = indexer.search("示例")
"""

from .local import LocalIndexer, IndexedDocument

__all__ = [
    "LocalIndexer",
    "IndexedDocument",
]
