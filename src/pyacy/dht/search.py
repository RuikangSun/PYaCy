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
from ..utils import (
    hash_to_words_exclude,
    word_to_hash,
    words_to_hash_query,
    yacy_base64_decode,
    dht_distance,
    simplecoding_decode,
    parse_search_resource,
)

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
        word_hash: 匹配的词哈希（如果有）。
        title: 页面标题。
        description: 页面描述/摘要文本。
        url: 页面完整 URL。
        ranking: 排名分数。
        size: 文档大小（字节）。
        word_count: 词数。
        last_modified: 最后修改时间戳。
        language: 语言代码。
    """

    url_hash: str = ""
    word_hash: str = ""
    title: str = ""
    description: str = ""
    url: str = ""
    ranking: float = 0.0
    size: int = 0
    word_count: int = 0
    last_modified: int = 0
    language: str = ""


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

    # 兼容 SearchResult 的统一接口
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
        max_peers: int = 20,
        iterative: bool = True,
        expand_factor: int = 3,
        **kwargs: Any,
    ) -> DHTSearchResult:
        """使用 DHT 哈希路由在已知节点池中执行全文搜索。

        **与 v0.2.x 的关键区别**: 不再随机选取 Senior 节点，而是：
        1. 对每个查询词计算词哈希
        2. 在已知节点中按 XOR 距离找到最近的 k 个「负责节点」
        3. 只向负责节点发起搜索（因为这正是 DHT 协议的设计）
        4. 若首轮无结果，自动扩大搜索范围（迭代扩展）

        Args:
            peers: 已知节点列表。
            my_hash: 本地节点哈希。
            query: 搜索查询（自然语言字符串）。
            count: 期望结果数。
            max_peers: 每轮最多查询的节点数。
            iterative: 是否启用迭代扩展（0 结果时自动扩大范围）。
            expand_factor: 迭代扩展时的倍增因子。
            **kwargs: 其他搜索参数。

        Returns:
            DHTSearchResult 实例。
        """
        # 筛选可连接的 Senior 节点
        senior_peers = [
            s for s in peers
            if s.is_reachable and s.is_senior() and s.base_url
        ]

        if not senior_peers:
            _logger.warning("无可连接的 Senior 节点用于搜索")
            return DHTSearchResult(success=False)

        # 对查询词计算词哈希，并找到负责节点
        query_words = _tokenize_query(query)
        if not query_words:
            _logger.warning("搜索查询无有效词元")
            return DHTSearchResult(success=False)

        word_hashes = [word_to_hash(w) for w in query_words]
        targets = _find_responsible_peers(
            word_hashes=word_hashes,
            peers=senior_peers,
            k=max_peers,
        )

        if not targets:
            _logger.warning("哈希路由未找到合适的负责节点")
            return DHTSearchResult(success=False)

        _logger.info(
            "DHT 哈希路由: 查询 '%s' (%d 个词哈希) → %d 个负责节点",
            query, len(word_hashes), len(targets),
        )

        # 首轮搜索
        result = self.search_multiple(
            targets=targets,
            my_hash=my_hash,
            query=query,
            count=count,
            **kwargs,
        )

        # 迭代扩展（如果无结果且启用了迭代）
        if iterative and not result.references and len(senior_peers) > max_peers:
            for iteration in range(1, 4):  # 最多 3 轮扩展
                expanded_k = max_peers * (expand_factor ** iteration)
                if expanded_k > len(senior_peers):
                    expanded_k = len(senior_peers)

                _logger.info(
                    "搜索扩展（第 %d 轮）: k=%d → k=%d",
                    iteration, max_peers, expanded_k,
                )

                expanded_targets = _find_responsible_peers(
                    word_hashes=word_hashes,
                    peers=senior_peers,
                    k=expanded_k,
                )
                # 排除已查询的节点
                already_queried = {t[0] for t in targets}
                new_targets = [
                    t for t in expanded_targets
                    if t[0] not in already_queried
                ]

                if not new_targets:
                    _logger.info("无可扩展的新节点")
                    break

                expanded_result = self.search_multiple(
                    targets=new_targets,
                    my_hash=my_hash,
                    query=query,
                    count=count,
                    **kwargs,
                )

                if expanded_result.references:
                    _logger.info(
                        "迭代扩展（第 %d 轮）成功: %d 条引用",
                        iteration, len(expanded_result.references),
                    )
                    return expanded_result

                targets = expanded_targets

        return result


# ---------------------------------------------------------------------------
# 响应解析
# ---------------------------------------------------------------------------


def _parse_search_response(response: P2PResponse) -> DHTSearchResult:
    """解析 DHT 搜索响应。

    YaCy DHT 搜索响应格式（key=value）::

        version=1.940
        uptime=76
        searchtime=95
        references=linux,shirt,arch,...     ← 标签云（逗号分隔的词）
        joincount=5871                      ← 参与节点数
        count=5                             ← 结果数量（新格式）
        resource0={hash=xxx,url=b|base64,descr=b|base64,...}  ← 搜索结果
        resource1={...}
        ...
        indexcount.<wordhash>=xxx            ← 词哈希的索引计数
        indexabstract.<wordhash>=xxx         ← 词哈希的索引摘要

    兼容旧格式（v0.3.0）::
        linkcount=3                         ← 链接数量（旧格式）
        references={hash1 wh1 http://x.com} ← URL 引用（旧格式）
        links=http://x.com                  ← 链接列表（旧格式）

    关键差异（v0.3.1 修复）：
    - 新格式：结果存储在 ``resource0``, ``resource1``, ... 字段中
    - 旧格式：结果存储在 ``references`` 和 ``links`` 字段中
    - 优先使用新格式（resourceN），如果不存在则回退到旧格式
    - ``references`` 字段在新格式中是标签云，在旧格式中是 URL 引用

    Args:
        response: P2P 协议响应。

    Returns:
        DHTSearchResult 实例。
    """
    data = response.data

    # 解析搜索耗时
    search_time = data.get("searchtime", "0")
    try:
        search_time_ms = int(search_time)
    except ValueError:
        search_time_ms = 0

    # 解析节点数
    join_count = response.get_int("joincount", 0)

    # 尝试解析新格式（resource0, resource1, ...）
    references, links = _parse_resources(data)
    
    # 获取结果数量
    # 优先使用 count 字段（新格式），其次使用 linkcount（旧格式）
    result_count = response.get_int("count", 0)
    if result_count == 0:
        result_count = response.get_int("linkcount", 0)
    
    # 如果没有 resource 字段，尝试旧格式解析
    if not references and not links:
        references = _parse_references(data.get("references", ""))
        links = _parse_links(data.get("links", ""))
        
        # 如果有旧格式的 linkcount 且我们还没有计算 link_count
        if result_count == 0:
            result_count = response.get_int("linkcount", 0)

    # 解析标签云（references 字段在新格式中是逗号分隔的词列表）
    tags = _parse_references_as_tags(data.get("references", ""))

    # 解析索引计数和摘要
    index_counts = _parse_index_counts(data)
    index_abstracts = _parse_index_abstracts(data)

    _logger.debug(
        "搜索响应: time=%dms, joincount=%d, count=%d, refs=%d, tags=%d",
        search_time_ms, join_count, result_count,
        len(references), len(tags),
    )

    return DHTSearchResult(
        success=True,
        search_time_ms=search_time_ms,
        references=references,
        links=links,
        link_count=result_count,
        join_count=join_count,
        raw=data,
    )


def _parse_references_as_tags(references_str: str) -> list[str]:
    """解析 references 字段为标签云。

    YaCy 搜索响应中的 ``references`` 字段实际上是逗号分隔的
    相关词/标签云，不是 URL 引用列表。

    Args:
        references_str: 逗号分隔的标签字符串。

    Returns:
        标签列表。
    """
    if not references_str.strip():
        return []
    return [tag.strip() for tag in references_str.split(",") if tag.strip()]


def _parse_resources(
    data: dict[str, str],
) -> tuple[list[DHTReference], list[str]]:
    """解析搜索响应中的 resource0, resource1, ... 字段。

    YaCy 搜索结果存储在编号连续的 resource 字段中，格式为：
    ``{hash=url_hash,url=b|base64_url,descr=b|base64_descr,...}``

    常见的 resource 字段：
    - hash: URL 的 YaCy 哈希
    - url: 页面 URL（SimpleCoding 编码）
    - descr: 页面描述/摘要（SimpleCoding 编码）
    - title: 页面标题（SimpleCoding 编码）
    - size: 文档大小
    - wordcount: 词数
    - lastModified: 最后修改时间
    - language: 语言代码
    - ranking: 排名分数

    Args:
        data: P2P 响应数据字典。

    Returns:
        (references, links) 元组：
        - references: DHTReference 列表
        - links: URL 字符串列表
    """
    references: list[DHTReference] = []
    links: list[str] = []
    seen_urls: set[str] = set()

    # 遍历 resource0, resource1, ..., resourceN
    idx = 0
    while True:
        key = f"resource{idx}"
        if key not in data:
            break

        resource_str = data[key]
        parsed = parse_search_resource(resource_str)

        if parsed:
            # 提取 URL（已解码 SimpleCoding）
            url = parsed.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                links.append(url)

            # 构建 DHTReference
            ref = DHTReference(
                url_hash=parsed.get("hash", ""),
                url=url,
                title=parsed.get("title", ""),
                description=parsed.get("descr", ""),
                size=_safe_int(parsed.get("size", "0")),
                word_count=_safe_int(parsed.get("wordcount", "0")),
                last_modified=_safe_int(parsed.get("lastModified", "0")),
                language=parsed.get("language", ""),
                ranking=_safe_float(parsed.get("ranking", "0")),
            )
            references.append(ref)

        idx += 1

    return references, links


def _parse_index_counts(data: dict[str, str]) -> dict[str, int]:
    """解析 indexcount.<wordhash> 字段。

    Args:
        data: P2P 响应数据字典。

    Returns:
        词哈希 → 索引计数 的映射。
    """
    result: dict[str, int] = {}
    for key, value in data.items():
        if key.startswith("indexcount."):
            word_hash = key[11:]  # 去掉 "indexcount." 前缀
            try:
                result[word_hash] = int(value)
            except ValueError:
                result[word_hash] = 0
    return result


def _parse_index_abstracts(data: dict[str, str]) -> dict[str, str]:
    """解析 indexabstract.<wordhash> 字段。

    Args:
        data: P2P 响应数据字典。

    Returns:
        词哈希 → 索引摘要 的映射。
    """
    result: dict[str, str] = {}
    for key, value in data.items():
        if key.startswith("indexabstract."):
            word_hash = key[14:]  # 去掉 "indexabstract." 前缀
            result[word_hash] = value
    return result


def _safe_int(value: str, default: int = 0) -> int:
    """安全地将字符串转换为整数。

    Args:
        value: 字符串值。
        default: 转换失败时的默认值。

    Returns:
        整数值。
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value: str, default: float = 0.0) -> float:
    """安全地将字符串转换为浮点数。

    Args:
        value: 字符串值。
        default: 转换失败时的默认值。

    Returns:
        浮点数值。
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _parse_references(references_str: str) -> list[DHTReference]:
    """解析引用字符串（v0.3.0 兼容格式）。

    保留此函数以兼容旧格式的引用响应，但新版解析优先使用 ``_parse_resources``。

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
            url_raw = parts[i + 1]
            # 解码 SimpleCoding (b|base64 或 p|plain)
            url = simplecoding_decode(url_raw)

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
        links_str: 换行分隔的链接列表（可能包含 SimpleCoding 编码）。

    Returns:
        URL 字符串列表（已解码 SimpleCoding）。
    """
    if not links_str.strip():
        return []
    result = []
    for line in links_str.splitlines():
        line = line.strip()
        if line:
            # 解码 SimpleCoding (b|base64 或 p|plain)
            decoded = simplecoding_decode(line)
            result.append(decoded)
    return result


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _find_responsible_peers(
    word_hashes: list[str],
    peers: list[Seed],
    *,
    k: int = 20,
) -> list[tuple[str, str]]:
    """找到词哈希在 DHT 哈希空间中的负责节点。

    对每个词哈希，计算与所有已知节点哈希的 XOR 距离，
    选择距离最近的 k 个节点作为该词的「负责节点」——按 DHT 协议，
    这些节点最有可能持有该词哈希对应的 RWI 数据。

    多个词哈希的负责节点合并去重后返回。

    Args:
        word_hashes: 词哈希列表（每个为 12 字符 YaCy Base64）。
        peers: 已知的可连接 Senior 节点列表。
        k: 每个词哈希选择的最近节点数。

    Returns:
        去重后的目标节点列表 ``[(url, hash), ...]``，按平均距离排序。
    """
    if not word_hashes or not peers:
        return []

    # 对每个词哈希，计算所有节点距离并排序
    # 收集所有候选 (url, hash, distance)
    candidate_scores: dict[str, tuple[str, str, float]] = {}
    # key = url, value = (url, hash, min_distance)

    for wh in word_hashes:
        scored: list[tuple[int, Seed]] = []
        for peer in peers:
            if not peer.base_url:
                continue
            try:
                dist = dht_distance(wh, peer.hash)
                scored.append((dist, peer))
            except (ValueError, IndexError):
                continue

        scored.sort(key=lambda x: x[0])

        # 每个词哈希选前 k 个
        for dist, peer in scored[:k]:
            url = peer.base_url  # type: ignore[assignment]
            if url not in candidate_scores:
                candidate_scores[url] = (url, peer.hash, float(dist))
            else:
                # 保留最小距离
                _, _, prev_dist = candidate_scores[url]
                if dist < prev_dist:
                    candidate_scores[url] = (url, peer.hash, float(dist))

    # 按距离排序（最近的在前）
    results = sorted(candidate_scores.values(), key=lambda x: x[2])
    return [(url, hsh) for url, hsh, _ in results]


def _tokenize_query(query: str) -> list[str]:
    """将搜索查询拆分为词元列表。

    简单的空格分割，过滤空字符串和太短的词。

    Args:
        query: 搜索查询字符串。

    Returns:
        词元列表。
    """
    return [w for w in query.strip().lower().split() if len(w) >= 1]
