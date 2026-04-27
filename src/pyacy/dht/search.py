# -*- coding: utf-8 -*-
"""PYaCy DHT 搜索模块。

本模块实现了通过 YaCy P2P DHT（分布式哈希表）进行全文搜索的功能，
包括：
- 搜索词 → 词哈希转换
- 向远程节点发起 DHT 搜索请求
- DHT 搜索响应的解析
- 搜索结果去重与排序

DHT 搜索原理:
    1. 将搜索词转换为 12 字符的词哈希
    2. 将词哈希发送到 Senior 节点
    3. 节点在本地 RWI（反向词索引）中查找匹配
    4. 返回 URL 引用列表（word references）
    5. 可选地请求摘要（abstracts）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..p2p.protocol import P2PProtocol, P2PResponse
from ..p2p.seed import Seed
from ..utils import hash_to_words_exclude, word_to_hash, words_to_hash_query, yacy_base64_decode

#: 日志记录器
_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DHT 搜索结果数据模型
# ---------------------------------------------------------------------------


@dataclass
class DHTReference:
    """DHT 搜索结果中的单条引用。

    RWI（反向词索引）中的一条记录，指向包含搜索词的 URL。

    Attributes:
        url_hash: URL 的 YaCy 哈希（12 字符 Base64）。
        word_hash: 匹配的词哈希。
        title: 页面标题（如果请求了摘要）。
        description: 页面描述/摘要文本。
        url: 页面完整 URL（如果请求了摘要）。
        ranking: 排名分数。
    """

    url_hash: str = ""
    word_hash: str = ""
    title: str = ""
    description: str = ""
    url: str = ""
    ranking: float = 0.0


@dataclass
class DHTSearchResult:
    """DHT 搜索的完整结果。

    Attributes:
        success: 搜索是否成功。
        search_time_ms: 搜索耗时（毫秒）。
        references: 引用列表（URL 哈希匹配）。
        links: 解析出的完整链接列表。
        link_count: 链接总数。
        join_count: 参与连接的节点数。
        raw: 原始响应数据。
    """

    success: bool = False
    search_time_ms: int = 0
    references: list[DHTReference] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    link_count: int = 0
    join_count: int = 0
    raw: dict[str, str] = field(default_factory=dict)

    # 兼容 Level 0 的 SearchResult 接口
    @property
    def total_results(self) -> int:
        """引用总数（即搜索命中数）。"""
        return len(self.references)

    @property
    def items(self) -> list[DHTReference]:
        """引用列表。"""
        return self.references


# ---------------------------------------------------------------------------
# DHT 搜索客户端
# ---------------------------------------------------------------------------


class DHTSearchClient:
    """YaCy DHT 搜索客户端。

    封装了 DHT 搜索的完整生命周期：
    1. 关键词 → 词哈希
    2. 向远程节点发送搜索请求
    3. 解析搜索结果

    使用示例::

        client = DHTSearchClient(protocol)
        result = client.search(
            target_url="http://peer:8090",
            target_hash="abc...",
            my_hash="def...",
            query="hello world",
            count=10,
        )
        for ref in result.references:
            print(ref.title, ref.url)
    """

    def __init__(self, protocol: P2PProtocol):
        """初始化 DHT 搜索客户端。

        Args:
            protocol: P2P 协议实例。
        """
        self.protocol: P2PProtocol = protocol

    # ------------------------------------------------------------------
    # 单节点搜索
    # ------------------------------------------------------------------

    def search(
        self,
        target_url: str,
        target_hash: str,
        my_hash: str,
        query: str,
        *,
        my_seed_str: str | None = None,
        count: int = 10,
        max_time_ms: int = 3000,
        max_distance: int = 3,
        language: str = "",
        prefer: str = "",
        exclude_words: list[str] | None = None,
        abstracts: str = "auto",
        contentdom: str = "all",
    ) -> DHTSearchResult:
        """在远程节点执行 DHT 搜索。

        Args:
            target_url: 目标节点 URL。
            target_hash: 目标节点哈希。
            my_hash: 本地节点哈希。
            query: 搜索查询（自然语言字符串）。
            my_seed_str: 本地种子字符串（可选）。
            count: 期望结果数（默认 10）。
            max_time_ms: 最大搜索时间（毫秒，默认 3000）。
            max_distance: 最大 DHT 跳数（默认 3）。
            language: 语言过滤（如 "zh", "en"）。
            prefer: 偏好排序方式。
            exclude_words: 排除词列表。
            abstracts: 摘要模式（"auto"/"true"/""）。
            contentdom: 内容域过滤（默认 "all"）。

        Returns:
            DHTSearchResult 实例。
        """
        # 将查询词拆分为词哈希
        query_words = _tokenize_query(query)
        query_hashes = words_to_hash_query(query_words)

        # 排除词哈希
        exclude_hashes = ""
        if exclude_words:
            exclude_hashes = hash_to_words_exclude(exclude_words)

        try:
            response = self.protocol.search(
                target_url=target_url,
                target_hash=target_hash,
                my_hash=my_hash,
                query_hashes=query_hashes,
                my_seed_str=my_seed_str,
                count=count,
                max_time=max_time_ms,
                max_dist=max_distance,
                language=language,
                prefer=prefer,
                contentdom=contentdom,
                exclude_hashes=exclude_hashes,
                abstracts=abstracts,
            )
            return _parse_search_response(response)
        except Exception as exc:
            _logger.warning("DHT 搜索失败 (%s): %s", target_url, exc)
            return DHTSearchResult(success=False)

    # ------------------------------------------------------------------
    # 多节点搜索
    # ------------------------------------------------------------------

    def search_multiple(
        self,
        targets: list[tuple[str, str]],
        my_hash: str,
        query: str,
        *,
        count: int = 10,
        max_time_ms: int = 3000,
        max_workers: int = 5,
        **kwargs: Any,
    ) -> DHTSearchResult:
        """在多个节点上并发执行 DHT 搜索，合并结果。

        Args:
            targets: 目标节点列表，每项为 ``(url, hash)``。
            my_hash: 本地节点哈希。
            query: 搜索查询。
            count: 每个节点期望结果数。
            max_time_ms: 每个节点的最大搜索时间。
            max_workers: 最大并发数。
            **kwargs: 其他搜索参数。

        Returns:
            合并后的 DHTSearchResult。
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        all_refs: list[DHTReference] = []
        all_links: list[str] = []
        seen_hashes: set[str] = set()
        total_time = 0
        total_joins = 0
        success_count = 0

        def _search_one(url: str, hsh: str) -> DHTSearchResult:
            return self.search(
                target_url=url,
                target_hash=hsh,
                my_hash=my_hash,
                query=query,
                count=count,
                max_time_ms=max_time_ms,
                **kwargs,
            )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_search_one, url, hsh): (url, hsh)
                for url, hsh in targets
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result.success:
                        success_count += 1
                        total_time = max(total_time, result.search_time_ms)
                        total_joins += result.join_count

                        # 去重合并引用
                        for ref in result.references:
                            if ref.url_hash not in seen_hashes:
                                seen_hashes.add(ref.url_hash)
                                all_refs.append(ref)

                        for link in result.links:
                            if link not in all_links:
                                all_links.append(link)

                except Exception as exc:
                    url, hsh = futures[future]
                    _logger.debug("搜索节点 %s 失败: %s", url, exc)

        _logger.info(
            "多节点搜索完成: %d/%d 成功, %d 个去重引用",
            success_count, len(targets), len(all_refs),
        )

        return DHTSearchResult(
            success=success_count > 0,
            search_time_ms=total_time,
            references=all_refs,
            links=all_links,
            link_count=len(all_links),
            join_count=total_joins,
        )

    # ------------------------------------------------------------------
    # 全文搜索（简化接口）
    # ------------------------------------------------------------------

    def fulltext_search(
        self,
        peers: list[Seed],
        my_hash: str,
        query: str,
        *,
        count: int = 20,
        max_peers: int = 5,
        **kwargs: Any,
    ) -> DHTSearchResult:
        """在已知节点池中执行全文搜索。

        自动筛选可连接的 Senior 节点。

        Args:
            peers: 已知节点列表。
            my_hash: 本地节点哈希。
            query: 搜索查询。
            count: 期望结果数。
            max_peers: 最多搜索的节点数。
            **kwargs: 其他搜索参数。

        Returns:
            DHTSearchResult 实例。
        """
        # 筛选可连接的 Senior 节点
        reachable = [
            s for s in peers
            if s.is_reachable and s.is_senior() and s.base_url
        ]

        if not reachable:
            _logger.warning("无可连接的 Senior 节点用于搜索")
            return DHTSearchResult(success=False)

        # 限制节点数量
        targets = [
            (s.base_url, s.hash)  # type: ignore[arg-type]
            for s in reachable[:max_peers]
        ]

        return self.search_multiple(
            targets=targets,
            my_hash=my_hash,
            query=query,
            count=count,
        )


# ---------------------------------------------------------------------------
# 响应解析
# ---------------------------------------------------------------------------


def _parse_search_response(response: P2PResponse) -> DHTSearchResult:
    """解析 DHT 搜索响应。

    YaCy DHT 搜索响应格式（key=value）::

        searchtime=<毫秒>
        references=<引用字符串>
        linkcount=<链接数>
        links=<链接字符串>
        joincount=<连接节点数>
        indexcount=<索引命中数>

    Args:
        response: P2P 协议响应。

    Returns:
        DHTSearchResult 实例。
    """
    data = response.data

    search_time = data.get("searchtime", "0")
    try:
        search_time_ms = int(search_time)
    except ValueError:
        search_time_ms = 0

    link_count = response.get_int("linkcount", 0)
    join_count = response.get_int("joincount", 0)

    # 解析引用
    references = _parse_references(data.get("references", ""))

    # 解析链接
    links = _parse_links(data.get("links", ""))

    return DHTSearchResult(
        success=True,
        search_time_ms=search_time_ms,
        references=references,
        links=links,
        link_count=link_count,
        join_count=join_count,
        raw=data,
    )


def _parse_references(references_str: str) -> list[DHTReference]:
    """解析引用字符串。

    引用格式（空格分隔的字段组）::

        urlhash{wordhash url wordhash ...}

    或每个引用一行，字段以空格或制表符分隔。

    Args:
        references_str: 引用字符串。

    Returns:
        DHTReference 列表。
    """
    refs: list[DHTReference] = []

    if not references_str.strip():
        return refs

    for line in references_str.splitlines():
        line = line.strip()
        if not line:
            continue

        # YaCy 使用 ``{urlhash wordhash url wordhash ...}`` 格式
        if line.startswith("{") and line.endswith("}"):
            line = line[1:-1]

        parts = line.split()
        if len(parts) < 2:
            continue

        # 第一个是 URL 哈希，后续是词哈希 + URL + 词哈希...
        url_hash = parts[0]

        i = 1
        while i + 1 < len(parts):
            word_hash = parts[i]
            url = parts[i + 1]

            ref = DHTReference(
                url_hash=url_hash,
                word_hash=word_hash,
                url=url,
            )
            refs.append(ref)
            i += 2

        # 如果只有词哈希没有 URL
        if i < len(parts) and len(refs) == 0:
            ref = DHTReference(
                url_hash=url_hash,
                word_hash=parts[i] if i < len(parts) else "",
            )
            refs.append(ref)

    return refs


def _parse_links(links_str: str) -> list[str]:
    """解析链接字符串。

    Args:
        links_str: 换行分隔的链接列表。

    Returns:
        URL 字符串列表。
    """
    if not links_str.strip():
        return []
    return [line.strip() for line in links_str.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _tokenize_query(query: str) -> list[str]:
    """将搜索查询拆分为词元列表。

    简单的空格分割，过滤空字符串和太短的词。

    Args:
        query: 搜索查询字符串。

    Returns:
        词元列表。
    """
    return [w for w in query.strip().lower().split() if len(w) >= 1]
