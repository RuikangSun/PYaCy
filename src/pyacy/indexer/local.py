# -*- coding: utf-8 -*-
"""PYaCy 本地全文索引实现。

使用 SQLite FTS5 实现本地网页内容的全文索引和检索。
设计原则:
    - 零外部依赖
    - 与 RWI 存储共享数据库路径
    - 支持 Agent 友好的元分词标签
    - 批量写入优化
    - CJK 预分词支持

使用示例::

    indexer = LocalIndexer("~/.pyacy/index.db")
    indexer.add_document(
        url="https://example.com",
        title="示例",
        content="这是内容...",
        tags=["example"],
    )
    results = indexer.search("示例")
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)
DEFAULT_DB_NAME: str = "local_index.db"


def _pretokenize_cjk(text: str) -> str:
    """CJK 文本预分词：在每个 CJK 字符之间插入空格。

    SQLite FTS5 的 unicode61 分词器按空白和标点拆分词元，
    不识别 CJK 字符边界。本函数将 "测试页面" 转换为 "测 试 页 面"，
    使每个汉字成为独立词元，从而支持中文全文检索。
    """
    result: list[str] = []
    for ch in text:
        cp = ord(ch)
        if (0x4E00 <= cp <= 0x9FFF or 
            0x3400 <= cp <= 0x4DBF or 
            0x20000 <= cp <= 0x2A6DF):
            result.append(" ")
            result.append(ch)
            result.append(" ")
        else:
            result.append(ch)
    return "".join(result)


@dataclass
class IndexedDocument:
    """已索引的文档。"""
    rowid: int = 0
    url: str = ""
    title: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    fetched_at: int = 0
    word_count: int = 0


class LocalIndexer:
    """本地全文索引器。

    使用 SQLite FTS5 实现网页内容的全文检索。
    通过手动管理 FTS 索引实现 CJK 预分词支持。
    """

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = Path.home() / ".pyacy" / DEFAULT_DB_NAME
        elif isinstance(db_path, str):
            db_path = Path(db_path)

        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)

        self._db_path: Path = db_path
        self._conn: sqlite3.Connection | None = None
        self._connect()
        self._create_tables()
        _logger.info("本地索引初始化: %s", self._db_path)

    def _connect(self) -> None:
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")

    def _create_tables(self) -> None:
        """创建索引表（禁用触发器，使用手动 FTS 管理）。"""
        assert self._conn is not None

        # 文档元数据表
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                url TEXT PRIMARY KEY,
                title TEXT DEFAULT '',
                content TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                fetched_at INTEGER NOT NULL,
                word_count INTEGER DEFAULT 0
            )
        """)

        # FTS5 全文索引虚拟表（独立存储，手动管理）
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
                url,
                title,
                content,
                tags,
                tokenize='unicode61 remove_diacritics 2'
            )
        """)

        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
        self._conn = None

    def __enter__(self) -> "LocalIndexer":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def add_document(
        self,
        url: str,
        *,
        title: str = "",
        content: str = "",
        tags: list[str] | None = None,
        fetched_at: int | None = None,
    ) -> bool:
        """添加或更新文档到索引。

        如果 URL 已存在，则更新已有文档。
        FTS 索引使用 CJK 预分词后的文本。
        """
        assert self._conn is not None

        now = fetched_at or int(time.time())
        tags_str = ",".join(tags) if tags else ""
        word_count = len(content.split()) if content else 0

        try:
            # 写入主表
            self._conn.execute("""
                INSERT OR REPLACE INTO documents
                (url, title, content, tags, fetched_at, word_count)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (url, title, content[:50000], tags_str, now, word_count))

            # 手动管理 FTS 索引（CJK 预分词）
            # 先删除旧的 FTS 记录，再插入新的
            self._conn.execute("DELETE FROM docs_fts WHERE url = ?", (url,))
            if title or content or tags_str:
                self._conn.execute("""
                    INSERT INTO docs_fts (url, title, content, tags)
                    VALUES (?, ?, ?, ?)
                """, (
                    url,
                    _pretokenize_cjk(title),
                    _pretokenize_cjk(content),
                    _pretokenize_cjk(tags_str),
                ))

            self._conn.commit()
            return True
        except sqlite3.Error as exc:
            _logger.error("文档索引失败: %s", exc)
            return False

    def add_from_crawl_result(self, result: Any) -> bool:
        """从 CrawlResult 添加文档。"""
        if not result.ok or not result.text:
            return False

        return self.add_document(
            url=result.final_url or result.url,
            title=result.title,
            content=result.text,
            fetched_at=result.fetched_at,
        )

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[IndexedDocument]:
        """全文检索文档。

        CJK 查询需要预分词。
        """
        assert self._conn is not None

        if not query.strip():
            return []

        # CJK 查询需要预分词
        fts_query = _pretokenize_cjk(query).strip()
        if not fts_query:
            return []

        try:
            cursor = self._conn.execute("""
                SELECT d.rowid, d.url, d.title, d.content, d.tags, d.fetched_at, d.word_count
                FROM documents d
                JOIN docs_fts f ON d.url = f.url
                WHERE docs_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, limit))

            return [self._row_to_doc(row) for row in cursor.fetchall()]

        except sqlite3.OperationalError as exc:
            # FTS5 查询失败时回退到 LIKE
            _logger.debug("FTS5 检索失败，回退到 LIKE: %s", exc)
            cursor = self._conn.execute("""
                SELECT rowid, url, title, content, tags, fetched_at, word_count
                FROM documents
                WHERE url LIKE ? OR title LIKE ? OR content LIKE ?
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", limit))

            return [self._row_to_doc(row) for row in cursor.fetchall()]

    def search_by_tag(
        self,
        tag: str,
        *,
        limit: int = 20,
    ) -> list[IndexedDocument]:
        """按标签检索文档。"""
        assert self._conn is not None

        cursor = self._conn.execute("""
            SELECT rowid, url, title, content, tags, fetched_at, word_count
            FROM documents
            WHERE tags LIKE ?
            LIMIT ?
        """, (f"%{tag}%", limit))

        return [self._row_to_doc(row) for row in cursor.fetchall()]

    def get_document(self, url: str) -> IndexedDocument | None:
        """按 URL 获取文档。"""
        assert self._conn is not None

        cursor = self._conn.execute("""
            SELECT rowid, url, title, content, tags, fetched_at, word_count
            FROM documents WHERE url = ?
        """, (url,))

        row = cursor.fetchone()
        return self._row_to_doc(row) if row else None

    def delete_document(self, url: str) -> bool:
        """删除文档。"""
        assert self._conn is not None

        self._conn.execute("DELETE FROM docs_fts WHERE url = ?", (url,))
        cursor = self._conn.execute("DELETE FROM documents WHERE url = ?", (url,))
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        """获取已索引文档总数。"""
        assert self._conn is not None
        cursor = self._conn.execute("SELECT COUNT(*) FROM documents")
        return cursor.fetchone()[0]

    def all_tags(self) -> list[str]:
        """获取所有标签列表。"""
        assert self._conn is not None
        cursor = self._conn.execute("SELECT DISTINCT tags FROM documents WHERE tags != ''")
        tags: set[str] = set()
        for row in cursor.fetchall():
            for tag in row[0].split(","):
                tag = tag.strip()
                if tag:
                    tags.add(tag)
        return sorted(tags)

    def stats(self) -> dict[str, Any]:
        """获取索引统计信息。"""
        assert self._conn is not None
        cursor = self._conn.execute("SELECT COUNT(*), SUM(word_count) FROM documents")
        row = cursor.fetchone()
        return {
            "total_documents": row[0],
            "total_words": row[1] or 0,
            "unique_tags": len(self.all_tags()),
            "db_path": str(self._db_path),
        }

    @staticmethod
    def _row_to_doc(row: tuple) -> IndexedDocument:
        """将数据库行转换为 IndexedDocument。"""
        tags_str = row[4] if row[4] else ""
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        return IndexedDocument(
            rowid=row[0],
            url=row[1],
            title=row[2],
            content=row[3],
            tags=tags,
            fetched_at=row[5],
            word_count=row[6],
        )

    def __repr__(self) -> str:
        return f"LocalIndexer(db={self._db_path}, docs={self.count()})"