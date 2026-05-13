# -*- coding: utf-8 -*-
"""PYaCy 搜索查询解析器。

解析 YaCy 兼容的高级搜索语法，提取操作符并提供客户端侧过滤。

YaCy 支持的搜索操作符（参考 https://yacy.net/operation/search-parameters/）：
    - ``site:domain`` — 限定搜索域名（不含子域名）
    - ``tld:tld`` — 限定顶级域名（含子域名）
    - ``inurl:phrase`` — URL 必须包含短语
    - ``filetype:ext`` — 限定文件扩展名
    - ``LANGUAGE:xx`` — 语言过滤（如 ``LANGUAGE:en``）
    - ``/protocol`` — 协议过滤（如 ``/https``, ``/ftp``）
    - ``author:name`` — 作者过滤
    - ``-word`` — 排除词（减号前缀）
    - ``NEAR`` — 邻近搜索标记
    - ``RECENT`` — 优先近期结果
    - ``on:date`` — 指定日期
    - ``from:date`` / ``to:date`` — 日期范围

PYaCy 扩展操作符（非 YaCy 标准，客户端侧过滤实现）：
    - ``intitle:phrase`` — 标题必须包含短语（基于 Solr title 字段）
    - ``inhtml:phrase`` — 正文必须包含短语（基于 Solr text_t 字段）
    - ``link:domain`` — 查找链接到指定域名的结果（仅 Solr API 模式）

使用示例::

    q = SearchQuery.parse("site:example.com filetype:pdf python tutorial")
    print(q.clean_query)     # "python tutorial"
    print(q.site)            # "example.com"
    print(q.filetype)        # "pdf"

    # 在 DHT 搜索结果上应用客户端过滤
    filtered = q.filter_results(dht_search_result)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

_logger = logging.getLogger(__name__)

# 正则表达式：匹配 YaCy 搜索操作符
# site:domain — 限定域名
_RE_SITE = re.compile(r'\bsite:(\S+)', re.IGNORECASE)
# tld:tld — 限定顶级域名
_RE_TLD = re.compile(r'\btld:(\S+)', re.IGNORECASE)
# inurl:phrase — URL 包含短语
_RE_INURL = re.compile(r'\binurl:(\S+)', re.IGNORECASE)
# filetype:ext — 文件扩展名
_RE_FILETYPE = re.compile(r'\bfiletype:(\S+)', re.IGNORECASE)
# LANGUAGE:xx — 语言代码
_RE_LANGUAGE = re.compile(r'\bLANGUAGE:(\S+)', re.IGNORECASE)
# /protocol — 协议过滤（/http, /https, /ftp, /smb, /file）
_RE_PROTOCOL = re.compile(r'(?<!\w)/(https?|ftp|smb|file)\b', re.IGNORECASE)
# author:name — 作者
_RE_AUTHOR = re.compile(r'\bauthor:(\S+)', re.IGNORECASE)
# -word — 排除词（减号后紧跟单词）
_RE_EXCLUDE = re.compile(r'(?<!\S)-(\w+)')
# NEAR — 邻近搜索
_RE_NEAR = re.compile(r'\bNEAR\b', re.IGNORECASE)
# RECENT — 优先近期
_RE_RECENT = re.compile(r'\bRECENT\b', re.IGNORECASE)
# on:date — 日期
_RE_ON = re.compile(r'\bon:(\d{4}/\d{2}/\d{2})', re.IGNORECASE)
# from:date / to:date — 日期范围
_RE_FROM = re.compile(r'\bfrom:(\d{4}/\d{2}/\d{2})', re.IGNORECASE)
_RE_TO = re.compile(r'\bto:(\d{4}/\d{2}/\d{2})', re.IGNORECASE)
# intitle:phrase — 标题包含短语（PYaCy 扩展，非 YaCy 标准）
_RE_INTITLE = re.compile(r'\bintitle:(\S+)', re.IGNORECASE)
# inhtml:phrase — 正文包含短语（PYaCy 扩展，非 YaCy 标准）
_RE_INHTML = re.compile(r'\binhtml:(\S+)', re.IGNORECASE)
# link:domain — 链接到指定域名（PYaCy 扩展，非 YaCy 标准）
_RE_LINK = re.compile(r'\blink:(\S+)', re.IGNORECASE)


@dataclass(frozen=True)
class SearchQuery:
    """解析后的搜索查询。

    所有字段在解析后不可变（frozen dataclass）。

    Attributes:
        raw: 原始查询字符串。
        clean_query: 移除所有操作符后的纯文本查询。
        site: site: 操作符值（域名）。
        tld: tld: 操作符值（顶级域名）。
        inurl: inurl: 操作符值（URL 中需包含的短语）。
        filetype: filetype: 操作符值（文件扩展名）。
        language: LANGUAGE: 操作符值（语言代码）。
        protocol: /protocol 操作符值（协议名）。
        author: author: 操作符值（作者名）。
        exclude_words: -word 排除词列表。
        near: 是否启用邻近搜索。
        recent: 是否优先近期结果。
        date_on: on: 日期值。
        date_from: from: 日期起始值。
        date_to: to: 日期终止值。
        intitle: intitle: 操作符值（标题需包含的短语，PYaCy 扩展）。
        inhtml: inhtml: 操作符值（正文需包含的短语，PYaCy 扩展）。
        link: link: 操作符值（链接目标域名，PYaCy 扩展）。
        has_filters: 是否包含至少一个过滤操作符。
    """

    raw: str = ""
    clean_query: str = ""
    site: str = ""
    tld: str = ""
    inurl: str = ""
    filetype: str = ""
    language: str = ""
    protocol: str = ""
    author: str = ""
    exclude_words: tuple[str, ...] = ()
    near: bool = False
    recent: bool = False
    date_on: str = ""
    date_from: str = ""
    date_to: str = ""
    intitle: str = ""
    inhtml: str = ""
    link: str = ""

    @property
    def has_filters(self) -> bool:
        """是否包含至少一个过滤操作符。"""
        return bool(
            self.site or self.tld or self.inurl or self.filetype
            or self.language or self.protocol or self.author
            or self.exclude_words or self.near or self.recent
            or self.date_on or self.date_from or self.date_to
            or self.intitle or self.inhtml or self.link
        )

    @classmethod
    def parse(cls, query: str) -> SearchQuery:
        """解析搜索查询字符串，提取所有操作符。

        解析流程：
        1. 依次用正则提取各操作符
        2. 从原始查询中移除已提取的操作符
        3. 清理多余空白，得到 clean_query

        Args:
            query: 原始搜索查询字符串。

        Returns:
            解析后的 SearchQuery 实例。
        """
        if not query or not query.strip():
            return cls(raw=query, clean_query="")

        remaining = query

        # 提取 site:
        site = ""
        m = _RE_SITE.search(remaining)
        if m:
            site = m.group(1).strip().lower()
            remaining = _RE_SITE.sub("", remaining)

        # 提取 tld:
        tld = ""
        m = _RE_TLD.search(remaining)
        if m:
            tld = m.group(1).strip().lower()
            remaining = _RE_TLD.sub("", remaining)

        # 提取 inurl:
        inurl = ""
        m = _RE_INURL.search(remaining)
        if m:
            inurl = m.group(1).strip().lower()
            remaining = _RE_INURL.sub("", remaining)

        # 提取 filetype:
        filetype = ""
        m = _RE_FILETYPE.search(remaining)
        if m:
            filetype = m.group(1).strip().lower()
            remaining = _RE_FILETYPE.sub("", remaining)

        # 提取 LANGUAGE:
        language = ""
        m = _RE_LANGUAGE.search(remaining)
        if m:
            language = m.group(1).strip().lower()
            remaining = _RE_LANGUAGE.sub("", remaining)

        # 提取 /protocol
        protocol = ""
        m = _RE_PROTOCOL.search(remaining)
        if m:
            protocol = m.group(1).strip().lower()
            remaining = _RE_PROTOCOL.sub("", remaining)

        # 提取 author:
        author = ""
        m = _RE_AUTHOR.search(remaining)
        if m:
            author = m.group(1).strip()
            remaining = _RE_AUTHOR.sub("", remaining)

        # 提取 -word 排除词
        exclude_words: list[str] = []
        for m in _RE_EXCLUDE.finditer(remaining):
            exclude_words.append(m.group(1).lower())
        if exclude_words:
            remaining = _RE_EXCLUDE.sub("", remaining)

        # 提取 NEAR
        near = bool(_RE_NEAR.search(remaining))
        if near:
            remaining = _RE_NEAR.sub("", remaining)

        # 提取 RECENT
        recent = bool(_RE_RECENT.search(remaining))
        if recent:
            remaining = _RE_RECENT.sub("", remaining)

        # 提取 on:
        date_on = ""
        m = _RE_ON.search(remaining)
        if m:
            date_on = m.group(1)
            remaining = _RE_ON.sub("", remaining)

        # 提取 from: / to:
        date_from = ""
        date_to = ""
        m = _RE_FROM.search(remaining)
        if m:
            date_from = m.group(1)
            remaining = _RE_FROM.sub("", remaining)
        m = _RE_TO.search(remaining)
        if m:
            date_to = m.group(1)
            remaining = _RE_TO.sub("", remaining)

        # 提取 intitle:（PYaCy 扩展）
        intitle = ""
        m = _RE_INTITLE.search(remaining)
        if m:
            intitle = m.group(1).strip().lower()
            remaining = _RE_INTITLE.sub("", remaining)

        # 提取 inhtml:（PYaCy 扩展）
        inhtml = ""
        m = _RE_INHTML.search(remaining)
        if m:
            inhtml = m.group(1).strip().lower()
            remaining = _RE_INHTML.sub("", remaining)

        # 提取 link:（PYaCy 扩展）
        link = ""
        m = _RE_LINK.search(remaining)
        if m:
            link = m.group(1).strip().lower()
            remaining = _RE_LINK.sub("", remaining)

        # 清理 clean_query
        clean_query = " ".join(remaining.split())

        return cls(
            raw=query,
            clean_query=clean_query,
            site=site,
            tld=tld,
            inurl=inurl,
            filetype=filetype,
            language=language,
            protocol=protocol,
            author=author,
            exclude_words=tuple(exclude_words),
            near=near,
            recent=recent,
            date_on=date_on,
            date_from=date_from,
            date_to=date_to,
            intitle=intitle,
            inhtml=inhtml,
            link=link,
        )

    def filter_references(self, references: list[Any]) -> list[Any]:
        """对 DHT 搜索结果应用客户端侧过滤。

        DHT 搜索协议本身不支持高级操作符（site:, filetype: 等），
        因此需要在获取结果后客户端侧过滤。

        支持的过滤条件：
        - site: — URL 域名精确匹配（不含子域名）
        - tld: — URL 域名以指定 TLD 结尾
        - inurl: — URL 包含指定短语
        - filetype: — URL 以指定扩展名结尾
        - exclude_words — 排除标题或描述中包含排除词的结果
        - protocol: — URL 协议匹配

        Args:
            references: DHTReference 列表。

        Returns:
            过滤后的 DHTReference 列表。
        """
        if not self.has_filters:
            return references

        filtered = list(references)

        # site: 过滤 — 精确域名匹配（不含子域名）
        if self.site:
            filtered = [
                r for r in filtered
                if self._match_site(r.url, self.site)
            ]

        # tld: 过滤 — 域名以 TLD 结尾
        if self.tld:
            filtered = [
                r for r in filtered
                if self._match_tld(r.url, self.tld)
            ]

        # inurl: 过滤 — URL 包含短语
        if self.inurl:
            filtered = [
                r for r in filtered
                if self.inurl in r.url.lower()
            ]

        # filetype: 过滤 — URL 以扩展名结尾或包含 .ext
        if self.filetype:
            ext = self.filetype.lstrip(".")
            filtered = [
                r for r in filtered
                if self._match_filetype(r.url, ext)
            ]

        # protocol: 过滤 — URL 协议匹配
        if self.protocol:
            proto = self.protocol.rstrip("://")
            filtered = [
                r for r in filtered
                if r.url.lower().startswith(proto + "://")
            ]

        # exclude_words: 排除标题/描述中包含排除词的结果
        if self.exclude_words:
            filtered = [
                r for r in filtered
                if not self._contains_excluded(r)
            ]

        # intitle: 过滤 — 标题必须包含短语（PYaCy 扩展）
        if self.intitle:
            filtered = [
                r for r in filtered
                if self._match_intitle(r, self.intitle)
            ]

        # inhtml: 过滤 — 正文/描述必须包含短语（PYaCy 扩展）
        if self.inhtml:
            filtered = [
                r for r in filtered
                if self._match_inhtml(r, self.inhtml)
            ]

        # link: 过滤 — 链接中包含目标域名（PYaCy 扩展）
        if self.link:
            filtered = [
                r for r in filtered
                if self._match_link(r, self.link)
            ]

        _logger.debug(
            "客户端过滤: %d → %d 条（site=%s, tld=%s, inurl=%s, filetype=%s, "
            "protocol=%s, intitle=%s, inhtml=%s, link=%s）",
            len(references), len(filtered),
            self.site, self.tld, self.inurl, self.filetype,
            self.protocol, self.intitle, self.inhtml, self.link,
        )
        return filtered

    def filter_links(self, links: list[str]) -> list[str]:
        """对链接列表应用客户端侧过滤。

        Args:
            links: URL 字符串列表。

        Returns:
            过滤后的 URL 列表。
        """
        if not self.has_filters:
            return links

        filtered = list(links)

        if self.site:
            filtered = [u for u in filtered if self._match_site(u, self.site)]
        if self.tld:
            filtered = [u for u in filtered if self._match_tld(u, self.tld)]
        if self.inurl:
            filtered = [u for u in filtered if self.inurl in u.lower()]
        if self.filetype:
            ext = self.filetype.lstrip(".")
            filtered = [u for u in filtered if self._match_filetype(u, ext)]
        if self.protocol:
            proto = self.protocol.rstrip("://")
            filtered = [u for u in filtered if u.lower().startswith(proto + "://")]
        # link: — 在 link 模式下，保留域名匹配的 URL
        if self.link:
            filtered = [u for u in filtered if self._match_link_url(u, self.link)]

        return filtered

    # ------------------------------------------------------------------
    # 匹配工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _match_site(url: str, domain: str) -> bool:
        """检查 URL 的域名是否精确匹配（不含子域名）。

        site:example.com 应匹配 www.example.com 但不匹配 other.com。
        YaCy 的 site: 不包含子域名，即 example.com 匹配
        example.com 但不匹配 sub.example.com。

        Args:
            url: 完整 URL。
            domain: 目标域名。

        Returns:
            域名是否匹配。
        """
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            # 精确匹配域名或 www. 前缀
            return host == domain or host == "www." + domain
        except Exception:
            return False

    @staticmethod
    def _match_tld(url: str, tld: str) -> bool:
        """检查 URL 的域名是否以指定 TLD 结尾。

        tld:co.uk 应匹配 example.co.uk 和 sub.example.co.uk。

        Args:
            url: 完整 URL。
            tld: 目标顶级域名。

        Returns:
            TLD 是否匹配。
        """
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            return host.endswith("." + tld) or host == tld
        except Exception:
            return False

    @staticmethod
    def _match_filetype(url: str, ext: str) -> bool:
        """检查 URL 是否以指定扩展名结尾。

        filetype:pdf 应匹配 report.pdf 和 /path/to/file.pdf。

        Args:
            url: 完整 URL。
            ext: 目标扩展名（不含点号）。

        Returns:
            扩展名是否匹配。
        """
        try:
            # 检查 URL 路径是否以 .ext 结尾
            path = urlparse(url).path.lower()
            if path.endswith("." + ext):
                return True
            # 也检查查询参数中是否有 .ext（如 download.php?file=report.pdf）
            query = urlparse(url).query.lower()
            return "." + ext in query
        except Exception:
            return False

    def _contains_excluded(self, ref: Any) -> bool:
        """检查引用的标题或描述是否包含排除词。"""
        title = getattr(ref, "title", "") or ""
        desc = getattr(ref, "description", "") or ""
        text = (title + " " + desc).lower()
        return any(w in text for w in self.exclude_words)

    @staticmethod
    def _match_intitle(ref: Any, phrase: str) -> bool:
        """检查引用的标题是否包含指定短语（intitle: 过滤）。

        Args:
            ref: DHTReference 对象。
            phrase: 要匹配的短语（已小写化）。

        Returns:
            标题中是否包含该短语。
        """
        title = (getattr(ref, "title", "") or "").lower()
        return phrase in title

    @staticmethod
    def _match_inhtml(ref: Any, phrase: str) -> bool:
        """检查引用的描述/正文是否包含指定短语（inhtml: 过滤）。

        注意：DHT 搜索结果通常只包含 snippet（摘要），
        完整正文需要 Solr API 查询。

        Args:
            ref: DHTReference 对象。
            phrase: 要匹配的短语（已小写化）。

        Returns:
            描述/摘要中是否包含该短语。
        """
        desc = (getattr(ref, "description", "") or "").lower()
        title = (getattr(ref, "title", "") or "").lower()
        return phrase in desc or phrase in title

    @staticmethod
    def _match_link(ref: Any, domain: str) -> bool:
        """检查引用的 URL 是否链接到指定域名（link: 过滤）。

        在 DHT 模式下，link: 的语义简化为：
        检查结果 URL 的域名是否匹配（因为 DHT 不返回反向链接）。
        完整的反向链接查询需要 Solr webgraph 核心。

        Args:
            ref: DHTReference 对象。
            domain: 目标域名（已小写化）。

        Returns:
            URL 域名是否匹配。
        """
        url = getattr(ref, "url", "") or ""
        try:
            host = urlparse(url).hostname or ""
            host = host.lower()
            return host == domain or host.endswith("." + domain)
        except Exception:
            return False

    @staticmethod
    def _match_link_url(url: str, domain: str) -> bool:
        """检查 URL 字符串的域名是否匹配指定域名（link: 过滤，纯 URL 版本）。

        与 _match_link 的区别：此方法直接接受 URL 字符串，
        用于 filter_links() 中的纯 URL 列表过滤。

        Args:
            url: 完整 URL 字符串。
            domain: 目标域名（已小写化）。

        Returns:
            URL 域名是否匹配。
        """
        try:
            host = urlparse(url).hostname or ""
            host = host.lower()
            return host == domain or host.endswith("." + domain)
        except Exception:
            return False

    def __repr__(self) -> str:
        parts = [f"clean={self.clean_query!r}"]
        if self.site:
            parts.append(f"site={self.site}")
        if self.tld:
            parts.append(f"tld={self.tld}")
        if self.inurl:
            parts.append(f"inurl={self.inurl}")
        if self.filetype:
            parts.append(f"filetype={self.filetype}")
        if self.language:
            parts.append(f"lang={self.language}")
        if self.protocol:
            parts.append(f"proto={self.protocol}")
        if self.exclude_words:
            parts.append(f"exclude={self.exclude_words}")
        if self.near:
            parts.append("near=True")
        if self.recent:
            parts.append("recent=True")
        if self.intitle:
            parts.append(f"intitle={self.intitle}")
        if self.inhtml:
            parts.append(f"inhtml={self.inhtml}")
        if self.link:
            parts.append(f"link={self.link}")
        return f"SearchQuery({', '.join(parts)})"
