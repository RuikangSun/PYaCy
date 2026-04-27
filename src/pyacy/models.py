# -*- coding: utf-8 -*-
"""PYaCy 数据模型。

本模块定义了 YaCy API 返回数据的 Python 数据类，
提供类型安全的访问方式和便捷的属性提取方法。

所有模型都使用 ``dataclasses.dataclass`` 实现，
支持从 JSON/XML 字典直接构造。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchResult:
    """单条搜索结果。

    对应 ``/yacysearch.json`` 响应中 ``channels[0].items``
    数组的单个元素。

    Attributes:
        title: 搜索结果标题。
        link: 目标 URL。
        description: 搜索结果摘要（含高亮标签）。
        pub_date: 发布日期字符串。
        size: 文档大小（字节）。
        size_name: 文档大小（人类可读）。
        host: 主机名。
        path: URL 路径。
        file: 文件名。
        guid: 唯一标识符。
        raw: 原始 JSON 字典，用于访问未建模的字段。
    """

    title: str = ""
    link: str = ""
    description: str = ""
    pub_date: str = ""
    size: int = 0
    size_name: str = ""
    host: str = ""
    path: str = ""
    file: str = ""
    guid: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_json_item(cls, item: dict[str, Any]) -> "SearchResult":
        """从 JSON 搜索结果条目构造 SearchResult。

        Args:
            item: YaCy JSON 搜索结果中的单个 item 字典。

        Returns:
            填充好的 SearchResult 实例。
        """
        return cls(
            title=item.get("title", ""),
            link=item.get("link", ""),
            description=item.get("description", ""),
            pub_date=item.get("pubDate", ""),
            size=int(item.get("sizename", "0").split()[0]) if item.get("sizename") else 0,
            size_name=item.get("sizename", ""),
            host=item.get("host", ""),
            path=item.get("path", ""),
            file=item.get("file", ""),
            guid=item.get("guid", ""),
            raw=item,
        )


@dataclass
class SearchResponse:
    """搜索响应。

    对应 ``/yacysearch.json`` 的完整 JSON 响应。

    Attributes:
        query: 原始搜索查询词。
        total_results: 结果总数。
        start_index: 起始索引（0-based）。
        items_per_page: 每页结果数。
        items: 搜索结果列表。
        top_words: 热门关键词列表。
        raw: 原始 JSON 字典，用于访问未建模的字段。
    """

    query: str = ""
    total_results: int = 0
    start_index: int = 0
    items_per_page: int = 0
    items: list[SearchResult] = field(default_factory=list)
    top_words: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "SearchResponse":
        """从 YaCy search.json 响应构造 SearchResponse。

        Args:
            data: YaCy 返回的完整 JSON 字典。

        Returns:
            填充好的 SearchResponse 实例。
        """
        channels = data.get("channels", [])
        if not channels:
            return cls(raw=data)

        channel = channels[0]
        items_raw = channel.get("items", [])

        items = [SearchResult.from_json_item(item) for item in items_raw]
        # 解析 topwords
        top_words_raw = channel.get("topwords", [])
        top_words = [w.get("word", "") if isinstance(w, dict) else str(w) for w in top_words_raw]

        return cls(
            query=data.get("searchTerms", ""),
            total_results=int(channel.get("totalResults", 0)),
            start_index=int(channel.get("startIndex", 0)),
            items_per_page=int(channel.get("itemsPerPage", 0)),
            items=items,
            top_words=top_words,
            raw=data,
        )

    @property
    def total_pages(self) -> int:
        """估算总页数。

        Returns:
            总页数。如果 items_per_page 为 0 则返回 0。
        """
        if self.items_per_page == 0:
            return 0
        return (self.total_results + self.items_per_page - 1) // self.items_per_page


@dataclass
class SuggestResult:
    """搜索建议条目。

    对应 ``/suggest.json`` 响应数组的单个元素。

    Attributes:
        word: 建议词条。
        raw: 原始 JSON 字典。
    """

    word: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class SuggestResponse:
    """搜索建议响应。

    对应 ``/suggest.json`` 的完整 JSON 响应。

    Attributes:
        suggestions: 搜索建议列表。
        raw: 原始响应数据。
    """

    suggestions: list[SuggestResult] = field(default_factory=list)
    raw: list[dict[str, Any]] = field(default_factory=list, repr=False)

    @classmethod
    def from_json(cls, data: list[dict[str, Any]]) -> "SuggestResponse":
        """从 JSON 数组构造 SuggestResponse。

        Args:
            data: JSON 数组，每个元素包含 suggestion 字段。

        Returns:
            SuggestResponse 实例。
        """
        suggestions = [
            SuggestResult(
                word=item.get("suggestion", ""),
                raw=item,
            )
            for item in data
        ]
        return cls(suggestions=suggestions, raw=data)


@dataclass
class PeerStatus:
    """YaCy 节点状态信息。

    对应 ``/api/status_p.xml`` 或 ``/api/status_p.json``
    的响应数据。

    Attributes:
        status: 节点状态描述（如 "running", "paused"）。
        uptime: 运行时间（毫秒）。
        total_memory: 总内存（字节）。
        free_memory: 空闲内存（字节）。
        index_size: Solr 索引大小（文档数）。
        crawls_active: 活跃爬虫任务数。
        raw: 原始 JSON 字典。
    """

    status: str = ""
    uptime: int = 0
    total_memory: int = 0
    free_memory: int = 0
    index_size: int = 0
    crawls_active: int = 0
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "PeerStatus":
        """从 JSON 字典构造 PeerStatus。

        Args:
            data: YaCy 状态 API 返回的 JSON 字典。

        Returns:
            PeerStatus 实例。
        """
        return cls(
            status=data.get("status", ""),
            uptime=int(data.get("uptime", 0)),
            total_memory=int(data.get("totalMemory", 0)),
            free_memory=int(data.get("freeMemory", 0)),
            index_size=int(data.get("indexSize", 0) or 0),
            crawls_active=int(data.get("crawlsActive", 0) or 0),
            raw=data,
        )

    @property
    def memory_used_mb(self) -> float:
        """已使用内存（MB）。

        Returns:
            已使用内存的兆字节数。
        """
        return (self.total_memory - self.free_memory) / (1024 * 1024)

    @property
    def uptime_hours(self) -> float:
        """运行时间（小时）。

        Returns:
            运行时间的小时数。
        """
        return self.uptime / (1000 * 3600)


@dataclass
class VersionInfo:
    """YaCy 版本信息。

    对应 ``/api/version.xml`` 的响应数据。

    Attributes:
        version: 主版本号字符串。
        svn_revision: SVN 修订号。
        build_date: 构建日期。
        java_version: Java 版本。
        raw: 原始 JSON 字典。
    """

    version: str = ""
    svn_revision: str = ""
    build_date: str = ""
    java_version: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "VersionInfo":
        """从 JSON 字典构造 VersionInfo。

        Args:
            data: YaCy 版本 API 返回的 JSON 字典。

        Returns:
            VersionInfo 实例。
        """
        return cls(
            version=data.get("version", ""),
            svn_revision=data.get("svnRevision", ""),
            build_date=data.get("buildDate", ""),
            java_version=data.get("javaVersion", ""),
            raw=data,
        )


@dataclass
class NetworkInfo:
    """YaCy 网络统计信息。

    对应 ``/Network.xml`` 的响应数据。

    Attributes:
        active_peers: 活跃节点数。
        passive_peers: 被动节点数。
        potential_peers: 潜在节点数。
        total_urls: 网络总 URL 数。
        peer_name: 本节点名称。
        peer_hash: 本节点哈希。
        raw: 原始 JSON 字典。
    """

    active_peers: int = 0
    passive_peers: int = 0
    potential_peers: int = 0
    total_urls: int = 0
    peer_name: str = ""
    peer_hash: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "NetworkInfo":
        """从 JSON 字典构造 NetworkInfo。

        Args:
            data: YaCy 网络统计 API 返回的 JSON 字典。

        Returns:
            NetworkInfo 实例。
        """
        peers = data.get("peers", {})
        own = peers.get("your", {})
        net_all = peers.get("all", {})
        return cls(
            active_peers=int(net_all.get("active", 0) or 0),
            passive_peers=int(net_all.get("passive", 0) or 0),
            potential_peers=int(net_all.get("potential", 0) or 0),
            total_urls=int(net_all.get("count", 0) or 0),
            peer_name=own.get("name", ""),
            peer_hash=own.get("hash", ""),
            raw=data,
        )


@dataclass
class PushResult:
    """文档推送结果。

    对应 ``/api/push_p.json`` 响应的单个文档推送结果。

    Attributes:
        index: 文档序号。
        url: 文档 URL。
        success: 是否推送成功。
        message: 推送结果消息。
    """

    index: int = 0
    url: str = ""
    success: bool = False
    message: str = ""


@dataclass
class PushResponse:
    """批量文档推送响应。

    对应 ``/api/push_p.json`` 的完整 JSON 响应。

    Attributes:
        total_count: 推送文档总数。
        success_count: 成功推送数。
        fail_count: 失败数。
        success_all: 是否全部成功。
        items: 各文档推送结果列表。
        raw: 原始 JSON 字典。
    """

    total_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    success_all: bool = False
    items: list[PushResult] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "PushResponse":
        """从 JSON 字典构造 PushResponse。

        Args:
            data: YaCy push API 返回的 JSON 字典。

        Returns:
            PushResponse 实例。
        """
        items = []
        for key, value in data.items():
            if not key.startswith("item-"):
                continue
            if isinstance(value, dict):
                items.append(
                    PushResult(
                        index=int(value.get("item", 0)),
                        url=value.get("url", ""),
                        success=value.get("success", "false") == "true",
                        message=value.get("message", ""),
                    )
                )

        return cls(
            total_count=int(data.get("count", 0)),
            success_count=int(data.get("countsuccess", 0)),
            fail_count=int(data.get("countfail", 0)),
            success_all=data.get("successall", "false") == "true",
            items=items,
            raw=data,
        )
