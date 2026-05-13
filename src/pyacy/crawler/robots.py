# -*- coding: utf-8 -*-
"""PYaCy robots.txt 解析与遵从模块。

实现 robots.txt 的获取、解析和 URL 可爬取性判断，
遵循 Google 的 robots.txt 规范（RFC 9309 子集）。

设计原则:
    - 纯 Python 标准库实现
    - 线程安全（每个 RobotsEntry 不可变）
    - 带缓存（避免重复请求同一域名的 robots.txt）
    - 支持 Sitemap 字段
    - 优雅降级：请求失败默认允许爬取

robots.txt 格式参考::

    User-agent: *
    Disallow: /admin/
    Disallow: /private
    Allow: /public/
    Crawl-delay: 2
    Sitemap: https://example.com/sitemap.xml

    User-agent: PYaCyCrawler
    Disallow: /no-pyacy/

使用示例::

    from pyacy.crawler.robots import RobotsCache

    cache = RobotsCache(user_agent="PYaCyCrawler")
    allowed = cache.can_fetch("https://example.com/admin/panel")  # False
    allowed = cache.can_fetch("https://example.com/index.html")   # True
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

#: 日志记录器
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RobotsRule:
    """单条 robots.txt 规则。

    Attributes:
        path: URL 路径前缀或模式。
        allowed: True=Allow, False=Disallow。
        pattern: 已编译的正则模式（如果路径含通配符）。
    """
    path: str
    allowed: bool
    pattern: re.Pattern | None = None


@dataclass(frozen=True)
class RobotsEntry:
    """解析后的 robots.txt 条目（针对一个 User-agent）。

    Attributes:
        user_agent: 匹配的 User-agent 名称。
        rules: 按顺序排列的 Allow/Disallow 规则列表。
        crawl_delay: Crawl-delay 值（秒），None 表示未指定。
        sitemaps: Sitemap URL 列表。
    """
    user_agent: str
    rules: tuple[RobotsRule, ...] = ()
    crawl_delay: float | None = None
    sitemaps: tuple[str, ...] = ()


@dataclass
class RobotsTxt:
    """一个域名的完整 robots.txt 解析结果。

    Attributes:
        url: robots.txt 的完整 URL。
        entries: 各 User-agent 对应的条目。
        fetched_at: 获取时间戳。
        status: HTTP 状态码（0 表示获取失败）。
        fetch_error: 获取错误信息。
    """
    url: str
    entries: tuple[RobotsEntry, ...] = ()
    fetched_at: float = 0.0
    status: int = 0
    fetch_error: str = ""

    @property
    def ok(self) -> bool:
        """是否成功获取并解析。"""
        return self.status == 200 and not self.fetch_error


class RobotsParser:
    """robots.txt 解析器。

    实现 RFC 9309 子集的 robots.txt 解析，包括：
    - User-agent 匹配（最具体的优先）
    - Allow/Disallow 规则（最长路径优先）
    - 通配符支持（* 和 $）
    - Crawl-delay
    - Sitemap

    使用示例::

        parser = RobotsParser()
        txt = parser.parse(robots_content, "https://example.com/robots.txt")
        entry = parser.match_entry(txt, "PYaCyCrawler")
        allowed = parser.is_allowed(entry, "/admin/panel")
    """

    # robots.txt 通配符转换：* → .*, $ → \$
    _WILDCARD_RE = re.compile(r"(\*|\$)")

    def parse(
        self,
        content: str,
        url: str = "",
        status: int = 200,
    ) -> RobotsTxt:
        """解析 robots.txt 内容。

        Args:
            content: robots.txt 原始文本。
            url: robots.txt 的完整 URL。
            status: HTTP 状态码。

        Returns:
            解析后的 RobotsTxt 实例。
        """
        entries = self._parse_entries(content)
        return RobotsTxt(
            url=url,
            entries=tuple(entries),
            fetched_at=time.time(),
            status=status,
        )

    def _parse_entries(self, content: str) -> list[RobotsEntry]:
        """解析所有 User-agent 条目。"""
        # 按 User-agent 分组
        groups: dict[str, list[dict[str, Any]]] = {}
        current_agents: list[str] = []
        crawl_delay: float | None = None
        sitemaps: list[str] = []

        for line in content.splitlines():
            line = line.strip()

            # 跳过空行和注释
            if not line or line.startswith("#"):
                continue

            # 分割字段和值
            if ":" not in line:
                continue
            field, _, value = line.partition(":")
            field = field.strip().lower()
            value = value.strip()

            if field == "user-agent":
                # 新的 User-agent 行，可能开始新的组
                if value:
                    current_agents.append(value.lower())

            elif field == "disallow" and value:
                rule = self._make_rule(value, allowed=False)
                for agent in current_agents:
                    groups.setdefault(agent, []).append(rule)

            elif field == "allow" and value:
                rule = self._make_rule(value, allowed=True)
                for agent in current_agents:
                    groups.setdefault(agent, []).append(rule)

            elif field == "crawl-delay":
                try:
                    crawl_delay = float(value)
                except ValueError:
                    pass

            elif field == "sitemap":
                if value:
                    sitemaps.append(value)

            elif field == "" and value == "":
                # 空行分隔组
                current_agents = []
                crawl_delay = None

        # 构建 RobotsEntry
        entries: list[RobotsEntry] = []
        for agent, rules in groups.items():
            entries.append(RobotsEntry(
                user_agent=agent,
                rules=tuple(rules),
                crawl_delay=crawl_delay,
                sitemaps=tuple(sitemaps),
            ))

        return entries

    def _make_rule(self, path: str, allowed: bool) -> RobotsRule:
        """创建单条规则，处理通配符。"""
        pattern = None

        # 检查是否含通配符
        if "*" in path or "$" in path:
            # 转换为正则表达式
            regex = re.escape(path)
            regex = regex.replace(r"\*", ".*").replace(r"\$$", "$")
            try:
                pattern = re.compile(regex, re.IGNORECASE)
            except re.error:
                pattern = None

        return RobotsRule(path=path, allowed=allowed, pattern=pattern)

    def match_entry(
        self,
        robots_txt: RobotsTxt,
        user_agent: str,
    ) -> RobotsEntry | None:
        """找到最匹配的 User-agent 条目。

        匹配规则（Google 规范）：
        1. 精确匹配（如 "Googlebot"）优先于模糊匹配
        2. 前缀匹配（如 "Googlebot/2.1" 匹配 "Googlebot"）
        3. 通配符 "*" 匹配所有

        Args:
            robots_txt: 解析后的 robots.txt。
            user_agent: 请求的 User-agent 字符串。

        Returns:
            最匹配的 RobotsEntry，或 None（无规则）。
        """
        if not robots_txt.entries:
            return None

        ua_lower = user_agent.lower()

        # 1. 精确匹配
        for entry in robots_txt.entries:
            if entry.user_agent == ua_lower:
                return entry

        # 2. 前缀匹配（UA 以 entry.user_agent 开头）
        best_prefix: RobotsEntry | None = None
        best_prefix_len = 0
        for entry in robots_txt.entries:
            if entry.user_agent != "*" and ua_lower.startswith(entry.user_agent):
                if len(entry.user_agent) > best_prefix_len:
                    best_prefix = entry
                    best_prefix_len = len(entry.user_agent)

        if best_prefix:
            return best_prefix

        # 3. 通配符 "*"
        for entry in robots_txt.entries:
            if entry.user_agent == "*":
                return entry

        return None

    def is_allowed(
        self,
        entry: RobotsEntry | None,
        url_path: str,
    ) -> bool:
        """检查 URL 路径是否被允许爬取。

        规则匹配（Google 规范）：
        - 按规则顺序逐一匹配
        - 最长匹配路径优先
        - Allow 优先于 Disallow（当路径长度相同时）
        - 无规则时默认允许

        Args:
            entry: User-agent 条目。
            url_path: URL 路径（如 "/admin/panel"）。

        Returns:
            是否允许爬取。
        """
        if not entry or not entry.rules:
            return True  # 无规则，允许

        # 按路径长度降序排列，最长路径优先匹配
        # 同长度时 Allow 优先
        sorted_rules = sorted(
            entry.rules,
            key=lambda r: (len(r.path), r.allowed),
            reverse=True,
        )

        for rule in sorted_rules:
            if self._matches(rule, url_path):
                return rule.allowed

        return True  # 无匹配规则，允许

    def get_crawl_delay(
        self,
        entry: RobotsEntry | None,
        default: float = 1.0,
    ) -> float:
        """获取 Crawl-delay 值。

        Args:
            entry: User-agent 条目。
            default: 默认延迟值。

        Returns:
            爬取延迟（秒）。
        """
        if entry and entry.crawl_delay is not None:
            return entry.crawl_delay
        return default

    @staticmethod
    def _matches(rule: RobotsRule, url_path: str) -> bool:
        """检查规则是否匹配 URL 路径。"""
        if rule.pattern:
            return bool(rule.pattern.search(url_path))
        # 前缀匹配
        return url_path.startswith(rule.path)


class RobotsCache:
    """带缓存的 robots.txt 管理器。

    每个域名只请求一次 robots.txt，结果缓存指定时间。

    使用示例::

        cache = RobotsCache(user_agent="PYaCyCrawler")
        if cache.can_fetch("https://example.com/page"):
            # 可以爬取
            delay = cache.get_crawl_delay("https://example.com/")
    """

    def __init__(
        self,
        *,
        user_agent: str = "PYaCyCrawler",
        timeout: int = 10,
        cache_ttl: float = 3600.0,
        default_delay: float = 1.0,
    ):
        """初始化缓存。

        Args:
            user_agent: 自身的 User-agent。
            timeout: 请求 robots.txt 的超时（秒）。
            cache_ttl: 缓存存活时间（秒，默认 1 小时）。
            default_delay: 默认爬取延迟（秒）。
        """
        self.user_agent = user_agent
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.default_delay = default_delay
        self._parser = RobotsParser()
        self._cache: dict[str, tuple[float, RobotsTxt]] = {}

    def can_fetch(self, url: str) -> bool:
        """检查 URL 是否允许爬取。

        Args:
            url: 完整 URL。

        Returns:
            是否允许。
        """
        entry = self._get_entry(url)
        parsed = urlparse(url)
        return self._parser.is_allowed(entry, parsed.path or "/")

    def get_crawl_delay(self, url: str) -> float:
        """获取指定域名的爬取延迟。

        Args:
            url: 完整 URL。

        Returns:
            爬取延迟（秒）。
        """
        entry = self._get_entry(url)
        return self._parser.get_crawl_delay(entry, self.default_delay)

    def get_sitemaps(self, url: str) -> list[str]:
        """获取指定域名的 Sitemap URL 列表。

        Args:
            url: 完整 URL。

        Returns:
            Sitemap URL 列表。
        """
        entry = self._get_entry(url)
        if entry:
            return list(entry.sitemaps)
        return []

    def _get_entry(self, url: str) -> RobotsEntry | None:
        """获取 URL 对应域名的 robots.txt 条目（带缓存）。"""
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        # 检查缓存
        if domain in self._cache:
            ts, robots_txt = self._cache[domain]
            if time.monotonic() - ts < self.cache_ttl:
                return self._parser.match_entry(robots_txt, self.user_agent)

        # 获取 robots.txt
        robots_txt = self._fetch_robots(domain)
        self._cache[domain] = (time.monotonic(), robots_txt)

        return self._parser.match_entry(robots_txt, self.user_agent)

    def _fetch_robots(self, domain: str) -> RobotsTxt:
        """获取并解析 robots.txt。"""
        robots_url = f"{domain}/robots.txt"

        try:
            req = Request(robots_url, headers={
                "User-Agent": self.user_agent,
                "Accept": "text/plain",
            })
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read(512 * 1024)  # 最大 512KB
                content = raw.decode("utf-8", errors="replace")
                return self._parser.parse(content, robots_url, resp.status)

        except HTTPError as exc:
            if exc.code == 404:
                # 404 = 无 robots.txt，默认允许所有
                _logger.debug("robots.txt 不存在 (%s): 默认允许", domain)
                return RobotsTxt(url=robots_url, status=404)
            _logger.debug("获取 robots.txt 失败 (%s): HTTP %d", domain, exc.code)
            return RobotsTxt(url=robots_url, status=exc.code, fetch_error=str(exc))

        except (URLError, TimeoutError, Exception) as exc:
            _logger.debug("获取 robots.txt 异常 (%s): %s", domain, exc)
            return RobotsTxt(url=robots_url, status=0, fetch_error=str(exc))

    def clear(self) -> None:
        """清空缓存。"""
        self._cache.clear()

    @property
    def cached_domains(self) -> int:
        """已缓存的域名数。"""
        return len(self._cache)
