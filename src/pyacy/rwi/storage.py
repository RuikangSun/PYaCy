# -*- coding: utf-8 -*-
"""PYaCy RWI 本地存储引擎。

使用 SQLite 实现 RWI（反向词索引）的本地持久化存储。
设计原则:
- 零外部依赖（SQLite 为 Python 标准库内置）
- 支持 FTS5 全文检索（unicode61 分词器 + CJK 预分词）
- TTL 自动过期清理
- WAL 模式支持并发读写
- 批量写入优化性能

CJK 分词策略:
SQLite FTS5 的 unicode61 分词器按空白和标点拆分词元，
不识别 CJK 字符边界，导致中文文本作为整体存储无法检索。
解决方案：写入 FTS 前在每个 CJK 字符之间插入空格，
使 unicode61 能正确将每个汉字作为独立词元索引。
"""
from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)
DEFAULT_TTL_SECONDS: int = 24 * 3600
DEFAULT_DB_NAME: str = "rwi.db"
DEFAULT_BATCH_SIZE: int = 500


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
class RWIEntry:
    """RWI 索引条目。"""
    word_hash: str = ""
    url_hash: str = ""
    url: str = ""
    title: str = ""
    description: str = ""
    size: int = 0
    word_count: int = 0
    last_modified: int = 0
    language: str = ""
    received_at: int = 0
    expires_at: int = 0


class RWIStorage:
    """RWI SQLite 存储引擎。"""
    
    def __init__(self, db_path: str | Path | None = None, *, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        if db_path is None:
            db_path = Path.home() / ".pyacy" / DEFAULT_DB_NAME
        elif isinstance(db_path, str):
            db_path = Path(db_path)
        
        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._db_path: Path = db_path
        self._ttl: int = ttl_seconds
        self._conn: sqlite3.Connection | None = None
        self._connect()
        self._create_tables()
        _logger.info("RWI 存储初始化：%s (TTL=%ds)", self._db_path, self._ttl)

    def _connect(self) -> None:
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")

    def _create_tables(self) -> None:
        assert self._conn is not None
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS rwi_index (
                word_hash TEXT NOT NULL,
                url_hash TEXT NOT NULL,
                url TEXT DEFAULT '',
                title TEXT DEFAULT '',
                description TEXT DEFAULT '',
                size INTEGER DEFAULT 0,
                word_count INTEGER DEFAULT 0,
                last_modified INTEGER DEFAULT 0,
                language TEXT DEFAULT '',
                received_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                PRIMARY KEY (word_hash, url_hash)
            )
        """)
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS rwi_fts USING fts5(
                url, title, description,
                content=rwi_index,
                content_rowid=rowid,
                tokenize='unicode61 remove_diacritics 2'
            )
        """)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_rwi_word_hash ON rwi_index(word_hash)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_rwi_expires ON rwi_index(expires_at)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_rwi_url_hash ON rwi_index(url_hash)")
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
        self._conn = None

    def __enter__(self) -> "RWIStorage":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def insert(self, entry: RWIEntry) -> bool:
        assert self._conn is not None
        now = int(time.time())
        if entry.received_at == 0:
            entry.received_at = now
        if entry.expires_at == 0:
            entry.expires_at = now + self._ttl
        
        try:
            self._conn.execute("""
                INSERT OR REPLACE INTO rwi_index
                (word_hash, url_hash, url, title, description, size, word_count, last_modified, language, received_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (entry.word_hash, entry.url_hash, entry.url, entry.title, entry.description,
                  entry.size, entry.word_count, entry.last_modified, entry.language,
                  entry.received_at, entry.expires_at))
            
            if entry.url or entry.title or entry.description:
                self._conn.execute("""
                    INSERT OR REPLACE INTO rwi_fts (rowid, url, title, description)
                    VALUES (
                        (SELECT rowid FROM rwi_index WHERE word_hash = ? AND url_hash = ?),
                        ?, ?, ?
                    )
                """, (entry.word_hash, entry.url_hash,
                      _pretokenize_cjk(entry.url),
                      _pretokenize_cjk(entry.title),
                      _pretokenize_cjk(entry.description)))
            
            self._conn.commit()
            return True
        except sqlite3.Error as exc:
            _logger.error("RWI 写入失败：%s", exc)
            return False

    def insert_batch(self, entries: list[RWIEntry]) -> int:
        assert self._conn is not None
        if not entries:
            return 0
        
        now = int(time.time())
        success_count = 0
        
        try:
            for entry in entries:
                if entry.received_at == 0:
                    entry.received_at = now
                if entry.expires_at == 0:
                    entry.expires_at = now + self._ttl
                
                self._conn.execute("""
                    INSERT OR REPLACE INTO rwi_index
                    (word_hash, url_hash, url, title, description, size, word_count, last_modified, language, received_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (entry.word_hash, entry.url_hash, entry.url, entry.title, entry.description,
                      entry.size, entry.word_count, entry.last_modified, entry.language,
                      entry.received_at, entry.expires_at))
                success_count += 1
            
            # 逐条更新 FTS 索引（CJK 需要预分词，rebuild 从 rwi_index 读取原始文本无法处理）
            for entry in entries:
                if entry.url or entry.title or entry.description:
                    self._conn.execute("""
                        INSERT OR REPLACE INTO rwi_fts (rowid, url, title, description)
                        VALUES (
                            (SELECT rowid FROM rwi_index WHERE word_hash = ? AND url_hash = ?),
                            ?, ?, ?
                        )
                    """, (entry.word_hash, entry.url_hash,
                          _pretokenize_cjk(entry.url),
                          _pretokenize_cjk(entry.title),
                          _pretokenize_cjk(entry.description)))
            
            self._conn.commit()
            _logger.debug("RWI 批量写入：%d/%d 条成功", success_count, len(entries))
            return success_count
        except sqlite3.Error as exc:
            _logger.error("RWI 批量写入失败：%s", exc)
            self._conn.rollback()
            return success_count

    def query_by_word_hash(self, word_hash: str) -> list[RWIEntry]:
        assert self._conn is not None
        now = int(time.time())
        cursor = self._conn.execute("""
            SELECT word_hash, url_hash, url, title, description, size, word_count,
                   last_modified, language, received_at, expires_at
            FROM rwi_index
            WHERE word_hash = ? AND expires_at > ?
        """, (word_hash, now))
        return [self._row_to_entry(row) for row in cursor.fetchall()]

    def query_by_url_hash(self, url_hash: str) -> list[RWIEntry]:
        assert self._conn is not None
        now = int(time.time())
        cursor = self._conn.execute("""
            SELECT word_hash, url_hash, url, title, description, size, word_count,
                   last_modified, language, received_at, expires_at
            FROM rwi_index
            WHERE url_hash = ? AND expires_at > ?
        """, (url_hash, now))
        return [self._row_to_entry(row) for row in cursor.fetchall()]

    def fulltext_search(self, query: str, *, limit: int = 20) -> list[RWIEntry]:
        """全文检索 RWI 条目。CJK 查询需要预分词。"""
        assert self._conn is not None
        if not query.strip():
            return []
        
        fts_query = _pretokenize_cjk(query).strip()
        if not fts_query:
            return []
        
        now = int(time.time())
        try:
            cursor = self._conn.execute("""
                SELECT i.word_hash, i.url_hash, i.url, i.title, i.description,
                       i.size, i.word_count, i.last_modified, i.language,
                       i.received_at, i.expires_at
                FROM rwi_index i
                JOIN rwi_fts f ON i.rowid = f.rowid
                WHERE rwi_fts MATCH ?
                  AND i.expires_at > ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, now, limit))
            return [self._row_to_entry(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError as exc:
            _logger.debug("FTS5 查询失败，回退到 LIKE: %s", exc)
            cursor = self._conn.execute("""
                SELECT word_hash, url_hash, url, title, description,
                       size, word_count, last_modified, language,
                       received_at, expires_at
                FROM rwi_index
                WHERE (url LIKE ? OR title LIKE ? OR description LIKE ?)
                  AND expires_at > ?
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", now, limit))
            return [self._row_to_entry(row) for row in cursor.fetchall()]

    def get_random_word_hashes(self, count: int = 10) -> list[str]:
        assert self._conn is not None
        now = int(time.time())
        cursor = self._conn.execute("""
            SELECT DISTINCT word_hash FROM rwi_index
            WHERE expires_at > ?
            ORDER BY RANDOM()
            LIMIT ?
        """, (now, count))
        return [row[0] for row in cursor.fetchall()]

    def cleanup_expired(self, *, batch_size: int = 1000) -> int:
        assert self._conn is not None
        now = int(time.time())
        total_deleted = 0
        
        while True:
            cursor = self._conn.execute("""
                SELECT rowid, word_hash, url_hash FROM rwi_index
                WHERE expires_at < ?
                LIMIT ?
            """, (now, batch_size))
            expired_rows = cursor.fetchall()
            if not expired_rows:
                break
            
            for rowid, word_hash, url_hash in expired_rows:
                self._conn.execute("DELETE FROM rwi_index WHERE rowid = ?", (rowid,))
                self._conn.commit()
            
            total_deleted += len(expired_rows)
        
        if total_deleted > 0:
            self._conn.execute("INSERT INTO rwi_fts(rwi_fts) VALUES('rebuild')")
            self._conn.commit()
        
        _logger.info("RWI 过期清理完成：共删除 %d 条", total_deleted)
        return total_deleted

    def count(self) -> int:
        assert self._conn is not None
        now = int(time.time())
        cursor = self._conn.execute("SELECT COUNT(*) FROM rwi_index WHERE expires_at > ?", (now,))
        return cursor.fetchone()[0]

    def count_by_word_hash(self, word_hash: str) -> int:
        assert self._conn is not None
        now = int(time.time())
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM rwi_index WHERE word_hash = ? AND expires_at > ?",
            (word_hash, now)
        )
        return cursor.fetchone()[0]

    def unique_word_hashes(self) -> int:
        assert self._conn is not None
        now = int(time.time())
        cursor = self._conn.execute(
            "SELECT COUNT(DISTINCT word_hash) FROM rwi_index WHERE expires_at > ?",
            (now,)
        )
        return cursor.fetchone()[0]

    def unique_url_hashes(self) -> int:
        assert self._conn is not None
        now = int(time.time())
        cursor = self._conn.execute(
            "SELECT COUNT(DISTINCT url_hash) FROM rwi_index WHERE expires_at > ?",
            (now,)
        )
        return cursor.fetchone()[0]

    def stats(self) -> dict[str, Any]:
        return {
            "total_entries": self.count(),
            "unique_word_hashes": self.unique_word_hashes(),
            "unique_url_hashes": self.unique_url_hashes(),
            "ttl_seconds": self._ttl,
            "db_path": str(self._db_path),
        }

    @staticmethod
    def _row_to_entry(row: tuple) -> RWIEntry:
        return RWIEntry(
            word_hash=row[0], url_hash=row[1], url=row[2], title=row[3],
            description=row[4], size=row[5], word_count=row[6],
            last_modified=row[7], language=row[8], received_at=row[9],
            expires_at=row[10],
        )

    def delete_by_url_hash(self, url_hash: str) -> int:
        """按 URL 哈希删除 RWI 条目。

        Args:
            url_hash: 要删除的 URL 哈希。

        Returns:
            删除的条目数。
        """
        assert self._conn is not None
        cursor = self._conn.execute(
            "DELETE FROM rwi_index WHERE url_hash = ?",
            (url_hash,)
        )
        self._conn.commit()
        return cursor.rowcount

    def delete_by_word_hash(self, word_hash: str) -> int:
        """按词哈希删除 RWI 条目。

        Args:
            word_hash: 要删除的词哈希。

        Returns:
            删除的条目数。
        """
        assert self._conn is not None
        cursor = self._conn.execute(
            "DELETE FROM rwi_index WHERE word_hash = ?",
            (word_hash,)
        )
        self._conn.commit()
        return cursor.rowcount

    def get_stats(self) -> dict[str, Any]:
        """获取存储统计信息。

        Returns:
            统计信息字典。
        """
        assert self._conn is not None
        total = self.count()
        active = self._conn.execute(
            "SELECT COUNT(*) FROM rwi_index WHERE expires_at > ?",
            (time.time(),)
        ).fetchone()[0]
        return {
            "total_entries": total,
            "active_entries": active,
            "expired_entries": total - active,
            "db_path": self._db_path,
            "ttl": self._ttl,
        }

    def __repr__(self) -> str:
        return f"RWIStorage(db={self._db_path}, entries={self.count()}, ttl={self._ttl}s)"
