# -*- coding: utf-8 -*-
"""PYaCy 基础爬虫实现。

实现了单页面抓取、文本提取、链接提取等基础爬虫功能。

设计原则:
    - 纯 Python 标准库（urllib + html.parser）
    - 遵守 robots.txt 礼仪
    - 可配置的 User-Agent 和超时
    - 自动处理编码问题

使用示例::

    crawler = SimpleCrawler()
    result = crawler.fetch("https://example.com")
    if result.ok:
        print(f"标题: {result.title}")
        print(f"文本: {result.text[:200]}")
        print(f"链接: {result.links[:5]}")
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .robots import RobotsCache

#: 日志记录器
_logger = logging.getLogger(__name__)

#: 默认 User-Agent
DEFAULT_USER_AGENT: str = "PYaCyCrawler"

#: 默认请求超时（秒）
DEFAULT_TIMEOUT: int = 15

#: 默认最大页面大小（字节）— 防止下载过大的页面
DEFAULT_MAX_SIZE: int = 5 * 1024 * 1024  # 5 MB

#: 爬取延迟（秒）— 遵守 robots.txt 礼仪
DEFAULT_CRAWL_DELAY: float = 1.0


@dataclass
class CrawlResult:
    """单次爬取的结果。

    Attributes:
        url: 请求的 URL。
        final_url: 重定向后的最终 URL。
        status: HTTP 状态码。
        title: 页面标题。
        text: 提取的纯文本内容。
        html: 原始 HTML 内容。
        links: 提取的链接列表。
        content_type: Content-Type 头。
        fetched_at: 抓取时间戳。
        elapsed_ms: 抓取耗时（毫秒）。
        error: 错误信息（如果失败）。
        headers: 响应头字典。
    """

    url: str = ""
    final_url: str = ""
    status: int = 0
    title: str = ""
    text: str = ""
    html: str = ""
    links: list[str] = field(default_factory=list)
    content_type: str = ""
    fetched_at: int = 0
    elapsed_ms: int = 0
    error: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """请求是否成功（HTTP 2xx）。"""
        return 200 <= self.status < 300 and not self.error

    @property
    def is_html(self) -> bool:
        """是否为 HTML 内容。"""
        return "text/html" in self.content_type.lower()


class _HTMLTextExtractor(HTMLParser):
    """从 HTML 中提取纯文本和链接。

    继承 html.parser.HTMLParser，遍历 DOM 树提取：
    - 纯文本内容（排除 script/style 标签）
    - 所有 <a href="..."> 链接
    - <title> 标签内容
    """

    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self.title: str = ""
        self._skip_tags: set[str] = {"script", "style", "noscript"}
        self._skip_depth: int = 0
        self._in_title: bool = False
        self._current_attrs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """处理开始标签。"""
        attrs_dict = {k: v for k, v in attrs if v is not None}

        if tag in self._skip_tags:
            self._skip_depth += 1

        if tag == "title":
            self._in_title = True

        if tag == "a":
            href = attrs_dict.get("href", "")
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        """处理结束标签。"""
        if tag in self._skip_tags and self._skip_depth > 0:
            self._skip_depth -= 1

        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        """处理文本数据。"""
        if self._skip_depth > 0:
            return

        stripped = data.strip()
        if not stripped:
            return

        if self._in_title:
            self.title = stripped

        self.text_parts.append(stripped)

    def get_text(self) -> str:
        """获取提取的纯文本。"""
        return " ".join(self.text_parts)

    def get_links(self) -> list[str]:
        """获取提取的链接列表（去重保序）。"""
        seen: set[str] = set()
        unique: list[str] = []
        for link in self.links:
            if link not in seen:
                seen.add(link)
                unique.append(link)
        return unique


class URLFilter:
    """URL 过滤器。

    基于正则表达式的 URL 包含/排除过滤。
    支持域名、路径、文件扩展名等多种过滤维度。

    使用示例::

        f = URLFilter(
            include_patterns=[r"\.html$", r"/blog/"],
            exclude_patterns=[r"/admin/", r"\.pdf$"],
        )
        f.matches("https://example.com/blog/post.html")  # True
        f.matches("https://example.com/admin/panel")      # False
    """

    def __init__(
        self,
        *,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ):
        """初始化过滤器。

        Args:
            include_patterns: 包含模式列表（正则表达式）。
                仅匹配这些模式的 URL 会被保留。
                空列表表示允许所有。
            exclude_patterns: 排除模式列表（正则表达式）。
                匹配这些模式的 URL 会被排除。
        """
        self._include = [
            re.compile(p, re.IGNORECASE) for p in (include_patterns or [])
        ]
        self._exclude = [
            re.compile(p, re.IGNORECASE) for p in (exclude_patterns or [])
        ]

    def matches(self, url: str) -> bool:
        """检查 URL 是否通过过滤。

        规则：
        1. 如果有 include 模式，URL 必须匹配至少一个
        2. URL 不能匹配任何 exclude 模式

        Args:
            url: 完整 URL。

        Returns:
            是否通过过滤。
        """
        # 包含过滤
        if self._include:
            if not any(p.search(url) for p in self._include):
                return False

        # 排除过滤
        if self._exclude:
            if any(p.search(url) for p in self._exclude):
                return False

        return True

    @property
    def has_filters(self) -> bool:
        """是否有任何过滤规则。"""
        return bool(self._include or self._exclude)


class CrawlScheduler:
    """爬取调度器。

    实现按域名的请求间隔控制（礼貌爬取）。
    不同域名可以并发，同域名串行且遵守间隔。

    使用示例::

        scheduler = CrawlScheduler(default_delay=5.0)
        scheduler.wait("https://example.com/a")  # 立即返回
        scheduler.wait("https://example.com/b")  # 等待 5 秒
        scheduler.wait("https://other.com/c")    # 立即返回（不同域名）
    """

    def __init__(self, *, default_delay: float = 5.0):
        """初始化调度器。

        Args:
            default_delay: 默认域名请求间隔（秒）。
        """
        self.default_delay = default_delay
        self._domain_delays: dict[str, float] = {}  # 域名 → 间隔
        self._last_requests: dict[str, float] = {}  # 域名 → 最后请求时间

    def set_domain_delay(self, domain: str, delay: float) -> None:
        """设置指定域名的请求间隔（通常来自 robots.txt Crawl-delay）。

        Args:
            domain: 域名（如 "example.com"）。
            delay: 请求间隔（秒）。
        """
        self._domain_delays[domain.lower()] = delay

    def get_delay(self, url: str) -> float:
        """获取 URL 对应域名的请求间隔。

        Args:
            url: 完整 URL。

        Returns:
            请求间隔（秒）。
        """
        domain = self._extract_domain(url)
        return self._domain_delays.get(domain, self.default_delay)

    def wait(self, url: str) -> float:
        """等待直到可以发送请求。

        Args:
            url: 完整 URL。

        Returns:
            实际等待时间（秒）。
        """
        domain = self._extract_domain(url)
        delay = self._domain_delays.get(domain, self.default_delay)
        now = time.monotonic()

        if domain in self._last_requests:
            elapsed = now - self._last_requests[domain]
            if elapsed < delay:
                wait_time = delay - elapsed
                time.sleep(wait_time)
                self._last_requests[domain] = time.monotonic()
                return wait_time

        self._last_requests[domain] = now
        return 0.0

    def record_request(self, url: str) -> None:
        """记录请求时间（不等待）。

        Args:
            url: 完整 URL。
        """
        domain = self._extract_domain(url)
        self._last_requests[domain] = time.monotonic()

    @staticmethod
    def _extract_domain(url: str) -> str:
        """从 URL 提取域名。"""
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return url.lower()


class SimpleCrawler:
    """简易网页爬虫。

    - 提供基础的网页抓取和内容提取功能。
    - 纯 Python 标准库实现，无需第三方依赖。
    - robots.txt 遵从（自动获取并缓存）
    - URL 包含/排除过滤
    - 按域名的请求间隔调度

    使用示例::

        crawler = SimpleCrawler()

        # 抓取单个页面（自动检查 robots.txt）
        result = crawler.fetch("https://example.com")
        if result.ok:
            print(result.title, result.text[:100])

        # 递归爬取（深度 2，排除 PDF）
        f = URLFilter(exclude_patterns=[r"\.pdf$"])
        crawler = SimpleCrawler(url_filter=f)
        results = crawler.crawl("https://example.com", depth=2)
    """

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: int = DEFAULT_TIMEOUT,
        max_size: int = DEFAULT_MAX_SIZE,
        crawl_delay: float = DEFAULT_CRAWL_DELAY,
        respect_robots: bool = True,
        url_filter: URLFilter | None = None,
        scheduler: CrawlScheduler | None = None,
    ):
        """初始化爬虫。

        Args:
            user_agent: HTTP User-Agent 头。
            timeout: 请求超时（秒）。
            max_size: 最大页面大小（字节）。
            crawl_delay: 连续请求间的默认延迟（秒）。
            respect_robots: 是否遵守 robots.txt（默认 True）。
            url_filter: URL 过滤器（可选）。
            scheduler: 爬取调度器（可选，不传则自动创建）。
        """
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_size = max_size
        self.crawl_delay = crawl_delay
        self.respect_robots = respect_robots
        self._last_request_time: float = 0.0

        # v0.4.1 新增组件
        self.url_filter = url_filter or URLFilter()
        self.scheduler = scheduler or CrawlScheduler(default_delay=crawl_delay)
        self._robots_cache: RobotsCache | None = None
        if respect_robots:
            self._robots_cache = RobotsCache(
                user_agent=user_agent,
                timeout=timeout,
                default_delay=crawl_delay,
            )

    # ------------------------------------------------------------------
    # 单页面抓取
    # ------------------------------------------------------------------

    def fetch(self, url: str, *, timeout: int | None = None) -> CrawlResult:
        """抓取单个页面。

        Args:
            url: 目标 URL。
            timeout: 请求超时（秒），None 使用默认值。

        Returns:
            CrawlResult 实例。
        """
        start_time = time.monotonic()
        result = CrawlResult(url=url, fetched_at=int(time.time()))

        # robots.txt 检查
        if self._robots_cache and not self._robots_cache.can_fetch(url):
            result.error = "robots.txt 禁止爬取"
            _logger.info("robots.txt 禁止: %s", url)
            return result

        # 调度器等待（按域名限速）
        self.scheduler.wait(url)

        try:
            req = Request(url, headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "identity",
            })

            with urlopen(req, timeout=timeout or self.timeout) as resp:
                # 限制读取大小
                raw = resp.read(self.max_size)
                result.status = resp.status
                result.final_url = resp.url
                result.content_type = resp.headers.get("Content-Type", "")
                result.headers = dict(resp.headers)

                # 自动检测编码
                encoding = self._detect_encoding(result.content_type, raw)
                result.html = raw.decode(encoding, errors="replace")

                # 提取文本和链接
                if result.is_html:
                    extractor = _HTMLTextExtractor()
                    try:
                        extractor.feed(result.html)
                    except Exception:
                        pass  # HTML 解析错误不阻塞
                    result.title = extractor.title
                    result.text = extractor.get_text()
                    result.links = self._resolve_links(
                        extractor.get_links(), url
                    )
                else:
                    result.text = result.html

            self._last_request_time = time.time()

        except HTTPError as exc:
            result.status = exc.code
            result.error = f"HTTP {exc.code}: {exc.reason}"
            _logger.warning("爬取失败 (%s): %s", url, result.error)

        except URLError as exc:
            result.error = f"URL 错误: {exc.reason}"
            _logger.warning("爬取失败 (%s): %s", url, result.error)

        except TimeoutError:
            result.error = f"超时 ({timeout or self.timeout}s)"
            _logger.warning("爬取超时: %s", url)

        except Exception as exc:
            result.error = f"异常: {exc}"
            _logger.warning("爬取异常 (%s): %s", url, exc)

        result.elapsed_ms = int((time.monotonic() - start_time) * 1000)
        return result

    # ------------------------------------------------------------------
    # 递归爬取
    # ------------------------------------------------------------------

    def crawl(
        self,
        start_url: str,
        *,
        depth: int = 1,
        max_pages: int = 50,
        same_domain: bool = True,
        timeout: int | None = None,
    ) -> list[CrawlResult]:
        """递归爬取网页。

        从起始 URL 开始，跟随页面链接递归爬取。

        Args:
            start_url: 起始 URL。
            depth: 最大爬取深度（0=仅起始页，1=起始页+直接链接）。
            max_pages: 最大爬取页面数。
            same_domain: 是否限制在同一域名内。
            timeout: 单次请求超时。

        Returns:
            所有爬取结果的列表。
        """
        results: list[CrawlResult] = []
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(start_url, 0)]  # (url, depth)

        while queue and len(results) < max_pages:
            url, current_depth = queue.pop(0)

            # 去重
            normalized = self._normalize_url(url)
            if normalized in visited:
                continue
            visited.add(normalized)

            # URL 过滤
            if not self.url_filter.matches(url):
                _logger.debug("URL 过滤排除: %s", url)
                continue

            # 抓取
            result = self.fetch(url, timeout=timeout)
            results.append(result)

            # 跟随链接（如果未达到最大深度）
            if result.ok and current_depth < depth:
                for link in result.links:
                    absolute = urljoin(url, link)
                    if same_domain:
                        if urlparse(absolute).netloc != urlparse(start_url).netloc:
                            continue
                    if self._normalize_url(absolute) not in visited:
                        queue.append((absolute, current_depth + 1))

        _logger.info(
            "递归爬取完成: %s → %d 个页面（深度=%d）",
            start_url, len(results), depth,
        )

        return results

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _enforce_delay(self) -> None:
        """遵守爬取延迟。"""
        if self._last_request_time > 0:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.crawl_delay:
                time.sleep(self.crawl_delay - elapsed)

    @staticmethod
    def _detect_encoding(content_type: str, raw: bytes) -> str:
        """从 Content-Type 和 HTML meta 标签检测编码。

        Args:
            content_type: Content-Type 头。
            raw: 原始字节。

        Returns:
            编码名称（默认 utf-8）。
        """
        # 从 Content-Type 头检测
        ct_match = re.search(r"charset=([^\s;]+)", content_type, re.IGNORECASE)
        if ct_match:
            return ct_match.group(1).strip().lower()

        # 从 HTML meta 标签检测（前 1024 字节）
        header = raw[:1024].decode("ascii", errors="ignore")
        meta_match = re.search(
            r'<meta[^>]+charset=["\']?([^"\'\s;>]+)',
            header,
            re.IGNORECASE,
        )
        if meta_match:
            return meta_match.group(1).strip().lower()

        return "utf-8"

    @staticmethod
    def _resolve_links(links: list[str], base_url: str) -> list[str]:
        """将相对链接解析为绝对链接。

        Args:
            links: 链接列表（可能包含相对路径）。
            base_url: 基础 URL。

        Returns:
            绝对链接列表（去重保序）。
        """
        seen: set[str] = set()
        resolved: list[str] = []

        for link in links:
            try:
                absolute = urljoin(base_url, link)
                if absolute not in seen and absolute.startswith(("http://", "https://")):
                    seen.add(absolute)
                    resolved.append(absolute)
            except Exception:
                continue

        return resolved

    @staticmethod
    def _normalize_url(url: str) -> str:
        """规范化 URL 用于去重。

        移除 fragment（#...）和 trailing slash。

        Args:
            url: 原始 URL。

        Returns:
            规范化后的 URL。
        """
        parsed = urlparse(url)
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            normalized += f"?{parsed.query}"
        return normalized.rstrip("/").lower()

    def __repr__(self) -> str:
        return (
            f"SimpleCrawler(ua={self.user_agent[:30]}..., "
            f"timeout={self.timeout}s, delay={self.crawl_delay}s)"
        )
