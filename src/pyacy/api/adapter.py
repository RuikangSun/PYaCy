# -*- coding: utf-8 -*-
"""PYaCy API 适配器实现。

提供统一的 API 接口，用于 GUI、Agent 和外部程序调用。
设计为与核心模块解耦，预留扩展接口。

核心功能:
    - 统一搜索（本地 RWI + 远程 DHT 并行）
    - 网络状态查询
    - RWI 存储管理
    - 本地索引管理
    - Pull 模式控制

使用示例::

    adapter = PYaCyAdapter()

    # 引导入网
    adapter.bootstrap()

    # 搜索
    results = adapter.search("python")
    print(f"找到 {results['total']} 条结果")

    # 统计
    print(adapter.get_network_status())
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..network import PYaCyNode
from ..rwi import RWIStorage, RWIPuller
from ..crawler import SimpleCrawler
from ..indexer import LocalIndexer

#: 日志记录器
_logger = logging.getLogger(__name__)


class PYaCyAdapter:
    """PYaCy 统一 API 适配器。

    封装核心模块，提供简洁的 dict/list 接口。
    预留 Agent 友好的扩展接口。

    使用示例::

        adapter = PYaCyAdapter()
        adapter.bootstrap()
        results = adapter.search("python tutorial")
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        rwi_db_path: str | Path | None = None,
        index_db_path: str | Path | None = None,
    ):
        """初始化 API 适配器。

        Args:
            name: 节点名称。
            rwi_db_path: RWI 存储数据库路径（None 使用默认）。
            index_db_path: 本地索引数据库路径（None 使用默认）。
        """
        # 核心节点
        self._node = PYaCyNode(name=name)

        # RWI 存储
        self._rwi_storage = RWIStorage(rwi_db_path)

        # RWI Pull 器
        self._rwi_puller = RWIPuller(self._node, self._rwi_storage)

        # 本地爬虫
        self._crawler = SimpleCrawler()

        # 本地索引
        self._indexer = LocalIndexer(index_db_path)

        # Pull 线程控制
        self._auto_pull_enabled = False

        _logger.info("PYaCy API 适配器初始化完成")

    # ------------------------------------------------------------------
    # 节点生命周期
    # ------------------------------------------------------------------

    def bootstrap(self, **kwargs) -> bool:
        """引导节点接入 P2P 网络。

        Args:
            **kwargs: 传递给 PYaCyNode.bootstrap 的参数。

        Returns:
            True 如果 bootstrap 成功。
        """
        result = self._node.bootstrap(**kwargs)
        if result:
            # 自动启动定期 Pull（后台）
            if self._auto_pull_enabled:
                self._rwi_puller.start_periodic_pull()

        return result

    def close(self) -> None:
        """关闭适配器，释放资源。"""
        # 停止 Pull 线程
        if self._rwi_puller.is_running:
            self._rwi_puller.stop_periodic_pull()

        # 关闭连接
        self._rwi_storage.close()
        self._indexer.close()
        self._node.close()

        _logger.info("PYaCy API 适配器已关闭")

    def __enter__(self) -> "PYaCyAdapter":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # 搜索接口
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        count: int = 20,
        offset: int = 0,
        use_local: bool = True,
        use_remote: bool = True,
        **kwargs,
    ) -> dict[str, Any]:
        """统一搜索接口。

        支持并行查询本地 RWI 和远程 DHT，返回合并结果。

        Args:
            query: 搜索查询字符串。
            count: 期望结果数。
            offset: 分页偏移量。
            use_local: 是否查询本地 RWI。
            use_remote: 是否查询远程 DHT。
            **kwargs: 其他搜索参数。

        Returns:
            搜索结果字典::

                {
                    "query": str,          # 原始查询
                    "total": int,          # 总结果数
                    "results": list,       # 结果列表
                    "local_count": int,    # 本地结果数
                    "remote_count": int,   # 远程结果数
                    "search_time_ms": int, # 搜索耗时
                }
        """
        import time
        start = time.monotonic()
        all_results: list[dict] = []
        seen_urls: set[str] = set()

        local_count = 0
        remote_count = 0

        # 并行执行本地和远程搜索（简化：串行执行）
        if use_local:
            local_results = self._search_local(query, count)
            for ref in local_results:
                if ref["url"] not in seen_urls:
                    seen_urls.add(ref["url"])
                    all_results.append(ref)
                    local_count += 1

        if use_remote and self._node.is_bootstrapped:
            remote_results = self._search_remote(query, count, **kwargs)
            for ref in remote_results:
                if ref["url"] not in seen_urls:
                    seen_urls.add(ref["url"])
                    all_results.append(ref)
                    remote_count += 1

        # 应用分页
        paged = all_results[offset:offset + count]

        elapsed_ms = int((time.monotonic() - start) * 1000)

        return {
            "query": query,
            "total": len(all_results),
            "results": paged,
            "local_count": local_count,
            "remote_count": remote_count,
            "search_time_ms": elapsed_ms,
            "has_local": use_local,
            "has_remote": use_remote and self._node.is_bootstrapped,
        }

    def _search_local(self, query: str, count: int) -> list[dict]:
        """本地 RWI 搜索。

        Args:
            query: 搜索查询。
            count: 期望结果数。

        Returns:
            结果列表。
        """
        from ..utils import word_to_hash

        word_hash = word_to_hash(query)
        entries = self._rwi_storage.query_by_word_hash(word_hash)[:count]

        results = []
        for entry in entries:
            results.append({
                "url": entry.url,
                "title": entry.title or "(无标题)",
                "description": entry.description[:200] if entry.description else "",
                "url_hash": entry.url_hash,
                "word_hash": entry.word_hash,
                "size": entry.size,
                "language": entry.language,
                "source": "local_rwi",
            })

        return results

    def _search_remote(self, query: str, count: int, **kwargs) -> list[dict]:
        """远程 DHT 搜索。

        Args:
            query: 搜索查询。
            count: 期望结果数。
            **kwargs: 其他搜索参数。

        Returns:
            结果列表。
        """
        try:
            dht_result = self._node.search(query, count=count, **kwargs)

            results = []
            for ref in dht_result.references:
                results.append({
                    "url": ref.url,
                    "title": ref.title or "(无标题)",
                    "description": ref.description[:200] if ref.description else "",
                    "url_hash": ref.url_hash,
                    "word_hash": ref.word_hash,
                    "size": ref.size,
                    "language": ref.language,
                    "source": "remote_dht",
                })

            return results
        except Exception as exc:
            _logger.warning("远程 DHT 搜索失败: %s", exc)
            return []

    # ------------------------------------------------------------------
    # 爬虫接口
    # ------------------------------------------------------------------

    def crawl(
        self,
        url: str,
        *,
        depth: int = 0,
        index: bool = True,
    ) -> dict[str, Any]:
        """爬取并索引网页。

        Args:
            url: 目标 URL。
            depth: 爬取深度（0=仅当前页）。
            index: 是否加入本地索引。

        Returns:
            爬取结果字典。
        """
        if depth > 0:
            results = self._crawler.crawl(url, depth=depth)
            indexed = 0
            for result in results:
                if result.ok and index:
                    if self._indexer.add_from_crawl_result(result):
                        indexed += 1
            return {
                "crawled": len(results),
                "indexed": indexed,
                "urls": [r.final_url or r.url for r in results if r.ok],
            }
        else:
            result = self._crawler.fetch(url)
            if result.ok and index:
                self._indexer.add_from_crawl_result(result)
            return {
                "crawled": 1 if result.ok else 0,
                "indexed": 1 if result.ok and index else 0,
                "url": result.final_url or result.url,
                "title": result.title,
                "error": result.error,
            }

    # ------------------------------------------------------------------
    # Pull 模式控制
    # ------------------------------------------------------------------

    def start_pull(self, *, interval: int = 300) -> bool:
        """启动定期 Pull。

        Args:
            interval: Pull 间隔（秒）。

        Returns:
            True 如果启动成功。
        """
        if self._rwi_puller.is_running:
            _logger.info("Pull 已在运行")
            return True

        self._rwi_puller.start_periodic_pull(interval=interval)
        return self._rwi_puller.is_running

    def stop_pull(self) -> None:
        """停止定期 Pull。"""
        self._rwi_puller.stop_periodic_pull()

    def pull_once(self) -> int:
        """执行一次 Pull。

        Returns:
            导入的 RWI 条目数。
        """
        return self._rwi_puller.pull_once()

    # ------------------------------------------------------------------
    # 状态查询接口
    # ------------------------------------------------------------------

    def get_network_status(self) -> dict[str, Any]:
        """获取网络状态。

        Returns:
            网络状态字典。
        """
        return self._node.get_peer_stats()

    def get_rwi_stats(self) -> dict[str, Any]:
        """获取 RWI 存储统计。

        Returns:
            RWI 统计字典。
        """
        stats = self._rwi_storage.stats()
        pull_stats = self._rwi_puller.stats()
        return {
            **stats,
            "pull": {
                "total_pulled": pull_stats["total_pulled"],
                "total_pulls": pull_stats["total_pulls"],
                "is_running": pull_stats["is_running"],
                "interval": pull_stats["interval"],
            },
        }

    def get_index_stats(self) -> dict[str, Any]:
        """获取本地索引统计。

        Returns:
            索引统计字典。
        """
        return self._indexer.stats()

    def get_all_stats(self) -> dict[str, Any]:
        """获取全部统计信息。

        Returns:
            完整统计字典。
        """
        return {
            "network": self.get_network_status(),
            "rwi": self.get_rwi_stats(),
            "index": self.get_index_stats(),
        }

    # ------------------------------------------------------------------
    # 代理属性
    # ------------------------------------------------------------------

    @property
    def node(self) -> PYaCyNode:
        """获取底层节点（高级用户用）。"""
        return self._node

    @property
    def rwi_storage(self) -> RWIStorage:
        """获取 RWI 存储（高级用户用）。"""
        return self._rwi_storage

    @property
    def indexer(self) -> LocalIndexer:
        """获取本地索引（高级用户用）。"""
        return self._indexer

    def __repr__(self) -> str:
        return (
            f"PYaCyAdapter(node={self._node.name}, "
            f"rwi={self._rwi_storage.count()}, "
            f"index={self._indexer.count()})"
        )