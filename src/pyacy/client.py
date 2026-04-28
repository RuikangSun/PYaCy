# -*- coding: utf-8 -*-
"""PYaCy HTTP 客户端核心模块。

本模块实现了与 YaCy 搜索引擎通信的 HTTP 客户端，
封装了搜索、状态查询、爬虫控制等核心 API 端点。

使用示例::

    from pyacy import YaCyClient

    client = YaCyClient("http://localhost:8090")
    results = client.search("python", resource="global")
    for item in results.items:
        print(item.title, item.link)

    status = client.status()
    print(f"节点运行时间: {status.uptime_hours:.1f} 小时")

设计原则:
    - 所有 API 方法返回强类型的数据模型对象，而非裸字典
    - 网络错误、超时、API 错误均映射为自定义异常
    - 请求前对关键参数进行校验，避免无效请求
    - 不依赖 YaCy GPL 代码，纯基于公开 API 文档实现
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .exceptions import (
    PYaCyAuthError,
    PYaCyConnectionError,
    PYaCyError,
    PYaCyResponseError,
    PYaCyServerError,
    PYaCyTimeoutError,
    PYaCyValidationError,
)
from .models import (
    NetworkInfo,
    PeerStatus,
    PushResponse,
    SearchResponse,
    SuggestResponse,
    VersionInfo,
)

# ---------------------------------------------------------------------------
# 模块级常量
# ---------------------------------------------------------------------------

#: 默认请求超时时间（秒）
_DEFAULT_TIMEOUT: float = 30.0

#: 默认最大重试次数
_DEFAULT_MAX_RETRIES: int = 3

#: 重试时的退避因子（指数退避）
_DEFAULT_BACKOFF_FACTOR: float = 0.5

#: 应触发重试的 HTTP 状态码集合
_RETRY_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

#: 日志记录器
_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# YaCyClient
# ---------------------------------------------------------------------------


class YaCyClient:
    """YaCy 搜索引擎 HTTP 客户端。

    封装了与 YaCy 节点交互的所有 HTTP 请求，
    提供类型安全的 API 访问方式。

    Attributes:
        base_url: YaCy 服务的基础 URL（如 ``http://localhost:8090``）。
        timeout: 默认请求超时时间（秒）。
        auth: (用户名, 密码) 元组，用于 HTTP Basic Auth。
        session: 底层 ``requests.Session`` 实例。
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8090",
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        auth: tuple[str, str] | None = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        verify_ssl: bool = True,
    ):
        """初始化 YaCyClient。

        Args:
            base_url: YaCy 服务的基础 URL，不需要以 ``/`` 结尾。
                默认为 ``http://localhost:8090``。
            timeout: 默认的 HTTP 请求超时时间（秒）。默认 30 秒。
            auth: HTTP Basic Auth 凭据，格式为 ``(用户名, 密码)``。
                如果 YaCy 开启了认证保护，需要提供此项。
            max_retries: 请求失败时的最大重试次数。默认 3 次。
            verify_ssl: 是否验证 SSL 证书。默认 True。
                如果 YaCy 使用自签名证书，可设为 False。

        Raises:
            PYaCyValidationError: 如果 base_url 格式无效。
        """
        # ---- 参数校验 ----
        url = base_url.rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise PYaCyValidationError(
                f"base_url 必须以 http:// 或 https:// 开头，当前值: {url!r}"
            )

        self.base_url: str = url
        self.timeout: float = timeout
        self.auth: tuple[str, str] | None = auth

        # ---- 构建 Session ----
        self.session = requests.Session()

        # 配置重试策略（指数退避）
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=_DEFAULT_BACKOFF_FACTOR,
            status_forcelist=list(_RETRY_STATUS_CODES),
            allowed_methods=["GET", "HEAD", "OPTIONS"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # 基础认证
        if auth:
            self.session.auth = auth

        # SSL 验证
        self.session.verify = verify_ssl

        # 默认请求头
        self.session.headers.update(
            {
                "User-Agent": "PYaCy/0.2.2 (Python YaCy Client)",
                "Accept": "application/json, text/xml, */*",
            }
        )

        _logger.info("YaCyClient 初始化完成: base_url=%s, timeout=%.1fs", url, timeout)

    # -------------------------------------------------------------------
    # 内部工具方法
    # -------------------------------------------------------------------

    def _build_url(self, path: str) -> str:
        """构建完整的 API URL。

        Args:
            path: API 路径，如 ``/yacysearch.json``。

        Returns:
            完整的 URL 字符串。
        """
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        timeout: float | None = None,
        expect_json: bool = True,
    ) -> requests.Response:
        """发送 HTTP 请求并处理通用错误。

        这是所有 API 调用的底层方法，负责：
        1. 发送请求
        2. 检查 HTTP 状态码
        3. 将网络/超时错误映射为自定义异常

        Args:
            method: HTTP 方法（GET / POST）。
            path: API 路径（相对于 base_url）。
            params: URL 查询参数。
            data: POST 表单数据。
            files: 上传文件。
            timeout: 超时时间（秒），None 则使用实例默认值。
            expect_json: 是否期望 JSON 响应。

        Returns:
            原始的 ``requests.Response`` 对象。

        Raises:
            PYaCyConnectionError: 网络连接失败。
            PYaCyTimeoutError: 请求超时。
            PYaCyAuthError: 认证失败（401/403）。
            PYaCyServerError: 服务端错误（5xx）。
            PYaCyResponseError: 其他非成功状态码。
        """
        url = self._build_url(path)
        timeout_val = timeout if timeout is not None else self.timeout
        cleaned_params = self._clean_params(params)

        _logger.debug("%s %s params=%s", method, url, cleaned_params)

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=cleaned_params,
                data=data,
                files=files,
                timeout=timeout_val,
            )
        except requests.exceptions.Timeout as exc:
            raise PYaCyTimeoutError(
                f"请求超时: {method} {url} (超时 {timeout_val}s)",
                timeout=timeout_val,
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise PYaCyConnectionError(
                f"无法连接到 YaCy 服务: {url}\n"
                f"请确认 YaCy 已启动且地址正确。",
                original_error=exc,
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise PYaCyConnectionError(
                f"请求发生未知错误: {method} {url}",
                original_error=exc,
            ) from exc

        # ---- 状态码检查 ----
        if response.status_code == 401:
            raise PYaCyAuthError(
                "认证失败: 需要提供有效的用户名和密码。"
                "请通过 auth 参数传入凭据。",
                status_code=401,
            )
        if response.status_code == 403:
            raise PYaCyAuthError(
                "访问被拒绝: 当前凭据无权访问此 API。",
                status_code=403,
            )
        if response.status_code >= 500:
            raise PYaCyServerError(
                f"YaCy 服务端错误 (HTTP {response.status_code})",
                status_code=response.status_code,
                response_body=response.text[:500],
            )
        if response.status_code >= 400:
            raise PYaCyResponseError(
                f"API 返回错误 (HTTP {response.status_code}): {response.text[:200]}",
                status_code=response.status_code,
                response_body=response.text,
            )

        return response

    @staticmethod
    def _clean_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
        """清理查询参数，移除 None 值。

        Args:
            params: 原始参数字典。

        Returns:
            移除 None 值后的参数字典。如果原字典为 None 或空，
            返回 None。
        """
        if params is None:
            return None
        return {k: v for k, v in params.items() if v is not None}

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """发送 GET 请求并返回 JSON 数据。

        Args:
            path: API 路径。
            params: 查询参数。

        Returns:
            解析后的 JSON 数据（可能是 dict 或 list）。

        Raises:
            PYaCyResponseError: 如果响应不是有效的 JSON。
        """
        response = self._request("GET", path, params=params)

        # 部分 API 返回 JSON 但 Content-Type 可能是 text/html
        try:
            return response.json()
        except ValueError as exc:
            raise PYaCyResponseError(
                f"无法解析 JSON 响应: {response.text[:300]}",
                status_code=response.status_code,
            ) from exc

    def _post_form(
        self,
        path: str,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> requests.Response:
        """发送 POST 请求（表单格式）。

        Args:
            path: API 路径。
            data: POST 表单字段。
            files: 上传的文件。

        Returns:
            HTTP 响应对象。
        """
        return self._request("POST", path, data=data, files=files)

    # -------------------------------------------------------------------
    # 搜索 API
    # -------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        resource: str = "local",
        maximum_records: int = 10,
        start_record: int = 0,
        content_dom: str | None = None,
        verify: str | None = None,
        url_mask_filter: str | None = None,
        prefer_mask_filter: str | None = None,
        language: str | None = None,
        navigators: str | None = None,
        timeout: float | None = None,
    ) -> SearchResponse:
        """执行搜索查询。

        对应 YaCy API ``/yacysearch.json``。

        Args:
            query: 搜索关键词。支持特殊语法如 ``/date``（按日期排序）、
                ``NEAR``（邻近搜索）、``LANGUAGE:en``（语言过滤）、
                ``inlink:``、``inurl:``、``tld:`` 等高级搜索操作符。
            resource: 搜索范围。``"local"`` 仅搜索本地索引，
                ``"global"`` 向 P2P 网络中所有节点发送搜索请求。
                默认 ``"local"``。
            maximum_records: 返回的最大结果数。未认证时限制为 10 条。
                默认 10。
            start_record: 结果起始偏移量（0-based）。
                用于分页，例如 ``start_record=10, maximum_records=10``
                返回第 11-20 条结果。默认 0。
            content_dom: 内容类型过滤。可选值: ``"text"`` | ``"image"``
                | ``"audio"`` | ``"video"`` | ``"app"``。
            verify: 结果验证策略。
                - ``"true"``: 验证 URL 并返回摘要片段
                - ``"false"``: 不验证，速度更快
                - ``"iffresh"``: 缓存新鲜时使用缓存
                - ``"ifexist"``: 有缓存就用缓存
                - ``"cacheonly"``: 只用缓存
            url_mask_filter: URL 过滤正则表达式。
                只返回 URL 匹配此正则的结果。
            prefer_mask_filter: URL 偏好正则。
                优先返回 URL 匹配此正则的结果。
            language: 语言代码过滤（如 ``"lang_en"``）。
            navigators: 导航器显示选项。``"all"`` 显示所有，
                ``"none"`` 不显示。默认 ``"all"``。
            timeout: 本次请求的超时时间（秒），None 则使用默认值。

        Returns:
            SearchResponse: 包含搜索结果的结构化对象。

        Raises:
            PYaCyValidationError: 如果 query 为空。
            PYaCyConnectionError: 网络连接失败。
            PYaCyTimeoutError: 请求超时。

        Example:
            >>> client = YaCyClient()
            >>> results = client.search("python", resource="global", maximum_records=20)
            >>> print(f"找到 {results.total_results} 条结果")
            >>> for item in results.items:
            ...     print(f"{item.title} — {item.link}")
        """
        if not query or not query.strip():
            raise PYaCyValidationError("搜索关键词不能为空")

        params = {
            "query": query.strip(),
            "resource": resource,
            "maximumRecords": maximum_records,
            "startRecord": start_record,
            "contentdom": content_dom,
            "verify": verify,
            "urlmaskfilter": url_mask_filter,
            "prefermaskfilter": prefer_mask_filter,
            "lr": language,
            "nav": navigators or "all",
        }

        data = self._get_json("/yacysearch.json", params=params)
        return SearchResponse.from_json(data)

    def suggest(self, query: str, *, timeout: float | None = None) -> SuggestResponse:
        """获取搜索建议（自动补全）。

        对应 YaCy API ``/suggest.json``。

        Args:
            query: 部分搜索关键词。
            timeout: 本次请求的超时时间（秒）。

        Returns:
            SuggestResponse: 搜索建议列表。

        Raises:
            PYaCyValidationError: 如果 query 为空。

        Example:
            >>> client = YaCyClient()
            >>> suggestions = client.suggest("pyth")
            >>> for s in suggestions.suggestions:
            ...     print(s.word)
        """
        if not query or not query.strip():
            raise PYaCyValidationError("搜索建议关键词不能为空")

        data = self._get_json("/suggest.json", params={"query": query.strip()})
        # 响应是 JSON 数组
        if isinstance(data, list):
            return SuggestResponse.from_json(data)
        return SuggestResponse(raw=[data] if isinstance(data, dict) else [])

    # -------------------------------------------------------------------
    # 状态与信息 API
    # -------------------------------------------------------------------

    def status(self, *, timeout: float | None = None) -> PeerStatus:
        """获取 YaCy 节点的运行状态。

        对应 YaCy API ``/api/status_p.json``（受保护的 API，
        通常需要从 localhost 访问或提供认证凭据）。

        Returns:
            PeerStatus: 节点状态信息（运行状态、内存、索引大小等）。

        Example:
            >>> client = YaCyClient()
            >>> status = client.status()
            >>> print(f"状态: {status.status}")
            >>> print(f"内存使用: {status.memory_used_mb:.0f} MB")
            >>> print(f"索引文档数: {status.index_size}")
        """
        data = self._get_json("/api/status_p.json")
        return PeerStatus.from_json(data)

    def version(self, *, timeout: float | None = None) -> VersionInfo:
        """获取 YaCy 版本信息。

        对应 YaCy API ``/api/version.json``。

        Returns:
            VersionInfo: 版本、构建日期、Java 版本等信息。

        Example:
            >>> client = YaCyClient()
            >>> vi = client.version()
            >>> print(f"YaCy {vi.version}, 构建日期 {vi.build_date}")
        """
        data = self._get_json("/api/version.json")
        return VersionInfo.from_json(data)

    def network(self, *, timeout: float | None = None) -> NetworkInfo:
        """获取 YaCy P2P 网络统计信息。

        对应 YaCy API ``/Network.json``。

        Returns:
            NetworkInfo: 活跃节点数、总 URL 数等网络统计信息。

        Example:
            >>> client = YaCyClient()
            >>> net = client.network()
            >>> print(f"活跃节点: {net.active_peers}")
            >>> print(f"网络总 URL: {net.total_urls}")
        """
        data = self._get_json("/Network.json")
        return NetworkInfo.from_json(data)

    # -------------------------------------------------------------------
    # 爬虫控制 API
    # -------------------------------------------------------------------

    def crawl_start(
        self,
        start_url: str,
        *,
        crawling_depth: int = 1,
        must_match: str | None = None,
        must_not_match: str | None = None,
        index_text: bool = True,
        index_media: bool = False,
        crawling_q: str | None = None,
        recrawl_cycle: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """启动网页爬虫任务。

        对应 YaCy 的 ``/Crawler_p.html`` 端点。

        Args:
            start_url: 爬虫起始 URL。可以是单个 URL 或以逗号分隔的多个 URL。
            crawling_depth: 爬取深度。
                - 0: 仅爬取起始页面
                - 1: 爬取起始页面及直接链接的页面
                - >1: 更深层爬取
                默认 1。
            must_match: URL 必须匹配的正则表达式。只有匹配的页面才会被爬取。
            must_not_match: URL 不得匹配的正则表达式。匹配的页面会被排除。
            index_text: 是否索引文本内容。默认 True。
            index_media: 是否索引媒体文件。默认 False。
            crawling_q: 爬虫入口选择。``"crawl_proxy"`` 使用代理爬虫。
            recrawl_cycle: 重新爬取周期。如 ``"daily"`` | ``"weekly"`` 等。
            timeout: 本次请求的超时时间（秒）。

        Returns:
            包含爬虫启动结果信息的字典。

        Raises:
            PYaCyValidationError: 如果 start_url 为空。

        Example:
            >>> client = YaCyClient()
            >>> result = client.crawl_start(
            ...     "https://example.com",
            ...     crawling_depth=1,
            ...     must_match="example\\.com/.*",
            ... )
            >>> print(result)
        """
        if not start_url or not start_url.strip():
            raise PYaCyValidationError("起始 URL 不能为空")

        data = {
            "crawlingstart": start_url.strip(),
            "crawlingDepth": str(crawling_depth),
            "indexText": "on" if index_text else "off",
            "indexMedia": "on" if index_media else "off",
            "bookmarkTitle": "",
            "bookmarkFolder": "/crawlStart",
        }
        if must_match:
            data["mustmatch"] = must_match
        if must_not_match:
            data["mustnotmatch"] = must_not_match
        if crawling_q:
            data["crawlingQ"] = crawling_q
        if recrawl_cycle:
            data["recrawl"] = recrawl_cycle

        response = self._post_form("/Crawler_p.html", data=data)
        # Crawler_p.html 返回 HTML 页面，因此尝试解析为 JSON 或直接返回文本
        return {
            "status_code": response.status_code,
            "message": "爬虫任务已提交",
            "start_url": start_url,
        }

    def crawl_start_expert(
        self,
        start_url: str,
        *,
        crawling_depth: int = 1,
        must_match: str | None = None,
        must_not_match: str | None = None,
        crawl_order: str | None = None,
        index_text: bool = True,
        index_media: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """以专家模式启动爬虫任务（更多控制选项）。

        对应 YaCy 的 ``/CrawlStartExpert.html`` 端点。

        Args:
            start_url: 爬虫起始 URL。
            crawling_depth: 爬取深度。默认 1。
            must_match: 必须匹配的正则。
            must_not_match: 不得匹配的正则。
            crawl_order: 爬取顺序。可选值: ``"fill"``（广度优先填充）、
                ``"load"``（广度优先加载）等。
            index_text: 是否索引文本。默认 True。
            index_media: 是否索引媒体。默认 False。
            timeout: 超时时间（秒）。

        Returns:
            包含爬虫启动结果信息的字典。

        Raises:
            PYaCyValidationError: 如果 start_url 为空。
        """
        if not start_url or not start_url.strip():
            raise PYaCyValidationError("起始 URL 不能为空")

        data = {
            "crawlingstart": start_url.strip(),
            "crawlingDepth": str(crawling_depth),
            "indexText": "on" if index_text else "off",
            "indexMedia": "on" if index_media else "off",
        }
        if must_match:
            data["mustmatch"] = must_match
        if must_not_match:
            data["mustnotmatch"] = must_not_match
        if crawl_order:
            data["crawlOrder"] = crawl_order

        response = self._post_form("/CrawlStartExpert.html", data=data)
        return {
            "status_code": response.status_code,
            "message": "专家模式爬虫任务已提交",
            "start_url": start_url,
        }

    # -------------------------------------------------------------------
    # 文档推送 API
    # -------------------------------------------------------------------

    def push_document(
        self,
        url: str,
        content: bytes | str,
        *,
        content_type: str = "text/html",
        collection: str | None = None,
        last_modified: str | None = None,
        title: str | None = None,
        keywords: str | None = None,
        commit: bool = False,
        synchronous: bool = False,
        timeout: float | None = None,
    ) -> PushResponse:
        """将单个文档推送到 YaCy 索引。

        对应 YaCy API ``/api/push_p.json``。

        此 API 使用 HTTP POST multipart/form-data 方式提交文档。
        文档会被 YaCy 内置解析器处理并写入 Solr 索引。

        Args:
            url: 文档的 URL（将作为搜索结果中的链接）。
            content: 文档内容（文本或二进制数据）。
            content_type: MIME 类型，如 ``"text/html"``、
                ``"text/plain"``、``"application/pdf"`` 等。
                默认 ``"text/html"``。
            collection: 文档所属的集合名称。用于搜索结果的分面导航。
            last_modified: 文档最后修改时间（RFC 1123 格式，如
                ``"Tue, 15 Nov 1994 12:45:26 GMT"``）。
            title: 媒体文档的标题（当 content_type 为图像/视频等时）。
            keywords: 媒体文档的关键词（空格分隔）。
            commit: 是否立即提交索引使其可搜索。默认 False。
                设为 True 会降低性能，仅推荐在少量文档时使用。
            synchronous: 是否同步处理。默认 False（异步处理，性能更优）。
            timeout: 超时时间（秒）。上传大文件时建议适当增加。

        Returns:
            PushResponse: 推送结果（成功/失败详情）。

        Raises:
            PYaCyValidationError: 如果 url 为空。

        Example:
            >>> client = YaCyClient()
            >>> result = client.push_document(
            ...     url="https://example.com/page.html",
            ...     content="<html><body>Hello World</body></html>",
            ...     content_type="text/html",
            ...     collection="test",
            ... )
            >>> print(f"推送成功: {result.success_all}")
        """
        if not url or not url.strip():
            raise PYaCyValidationError("文档 URL 不能为空")

        # 构建 multipart 数据
        data_fields = {
            "count": "1",
            "url-0": url.strip(),
            "synchronous": "true" if synchronous else "false",
            "commit": "true" if commit else "false",
        }
        if collection:
            data_fields["collection-0"] = collection

        # 构建响应头
        response_headers = [f"Content-Type:{content_type}"]
        if last_modified:
            response_headers.append(f"Last-Modified:{last_modified}")
        if title:
            response_headers.append(f"X-YaCy-Media-Title:{title}")
        if keywords:
            response_headers.append(f"X-YaCy-Media-Keywords:{keywords}")
        data_fields["responseHeader-0"] = response_headers

        # 将 content 转换为字节
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

        files = {"data-0": ("document", content_bytes, content_type)}

        # 使用 multipart/form-data 发送
        response = self._request(
            "POST",
            "/api/push_p.json",
            data=data_fields,
            files=files,
            timeout=timeout,
        )
        return PushResponse.from_json(response.json())

    def push_documents_batch(
        self,
        documents: list[dict[str, Any]],
        *,
        commit: bool = False,
        synchronous: bool = False,
        timeout: float | None = None,
    ) -> PushResponse:
        """批量推送多个文档到 YaCy 索引。

        对应 YaCy API ``/api/push_p.json`` 的批量模式。

        Args:
            documents: 文档列表，每个元素为包含以下键的字典：
                - ``url`` (必填): 文档 URL
                - ``content`` (必填): 文档内容（str 或 bytes）
                - ``content_type`` (可选): MIME 类型，默认 ``"text/html"``
                - ``collection`` (可选): 集合名称
                - ``last_modified`` (可选): 最后修改时间
                - ``title`` (可选): 媒体标题
                - ``keywords`` (可选): 关键词
            commit: 是否立即提交。默认 False。
            synchronous: 是否同步处理。默认 False。
            timeout: 超时时间（秒）。

        Returns:
            PushResponse: 批量推送结果。

        Raises:
            PYaCyValidationError: 如果文档列表为空。
        """
        if not documents:
            raise PYaCyValidationError("文档列表不能为空")

        count = len(documents)
        data_fields: dict[str, Any] = {
            "count": str(count),
            "synchronous": "true" if synchronous else "false",
            "commit": "true" if commit else "false",
        }
        files: dict[str, Any] = {}

        for i, doc in enumerate(documents):
            url = doc.get("url", "")
            if not url:
                raise PYaCyValidationError(f"第 {i} 个文档缺少 url")

            data_fields[f"url-{i}"] = url

            content = doc.get("content", "")
            if isinstance(content, str):
                content = content.encode("utf-8")
            content_type = doc.get("content_type", "text/html")
            files[f"data-{i}"] = (f"document-{i}", content, content_type)

            if doc.get("collection"):
                data_fields[f"collection-{i}"] = doc["collection"]

            # 构建响应头
            headers_list = [f"Content-Type:{content_type}"]
            if doc.get("last_modified"):
                headers_list.append(f"Last-Modified:{doc['last_modified']}")
            if doc.get("title"):
                headers_list.append(f"X-YaCy-Media-Title:{doc['title']}")
            if doc.get("keywords"):
                headers_list.append(f"X-YaCy-Media-Keywords:{doc['keywords']}")
            data_fields[f"responseHeader-{i}"] = headers_list

        response = self._request(
            "POST",
            "/api/push_p.json",
            data=data_fields,
            files=files,
            timeout=timeout,
        )
        return PushResponse.from_json(response.json())

    # -------------------------------------------------------------------
    # 索引管理 API
    # -------------------------------------------------------------------

    def delete_index(
        self,
        *,
        url: str | None = None,
        host: str | None = None,
        delete_all: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """从 Solr 索引中删除文档。

        对应 YaCy API ``/IndexDeletion_p.html``。

        Args:
            url: 要删除的完整文档 URL。
            host: 要删除的主机名下所有文档。
            delete_all: 如果为 True，清空整个索引（慎用！）。
            timeout: 超时时间（秒）。

        Returns:
            删除操作结果信息。

        Raises:
            PYaCyValidationError: 如果没有指定删除目标。

        Example:
            >>> client = YaCyClient()
            >>> result = client.delete_index(url="https://example.com/page.html")
        """
        if not delete_all and not url and not host:
            raise PYaCyValidationError("必须指定至少一个删除目标: url、host 或 delete_all=True")

        data: dict[str, str] = {}
        if delete_all:
            data["deleteall"] = "true"
        if url:
            data["url"] = url
        if host:
            data["host"] = host

        response = self._post_form("/IndexDeletion_p.html", data=data)
        return {
            "status_code": response.status_code,
            "message": "索引删除请求已提交",
        }

    # -------------------------------------------------------------------
    # 黑名单管理 API
    # -------------------------------------------------------------------

    def get_blacklists(self, *, timeout: float | None = None) -> dict[str, Any]:
        """获取所有黑名单的元数据列表。

        对应 YaCy API ``/api/blacklists/get_metadata_p.json``。

        Returns:
            黑名单元数据字典。

        Example:
            >>> client = YaCyClient()
            >>> lists = client.get_blacklists()
        """
        return self._get_json("/api/blacklists/get_metadata_p.json")

    def get_blacklist(self, list_name: str, *, timeout: float | None = None) -> dict[str, Any]:
        """获取指定黑名单的内容。

        对应 YaCy API ``/api/blacklists/get_list_p.json``。

        Args:
            list_name: 黑名单名称。

        Returns:
            黑名单内容。

        Raises:
            PYaCyValidationError: 如果 list_name 为空。
        """
        if not list_name or not list_name.strip():
            raise PYaCyValidationError("黑名单名称不能为空")
        return self._get_json("/api/blacklists/get_list_p.json", params={"list": list_name.strip()})

    def add_blacklist_entry(
        self,
        list_name: str,
        entry: str,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """向黑名单添加条目。

        对应 YaCy API ``/api/blacklists/add_entry_p.json``。

        Args:
            list_name: 黑名单名称。
            entry: 要添加的条目（URL 模式或主机名）。
            timeout: 超时时间（秒）。

        Returns:
            操作结果字典。

        Raises:
            PYaCyValidationError: 如果参数为空。
        """
        if not list_name or not list_name.strip():
            raise PYaCyValidationError("黑名单名称不能为空")
        if not entry or not entry.strip():
            raise PYaCyValidationError("黑名单条目不能为空")

        return self._get_json(
            "/api/blacklists/add_entry_p.json",
            params={"list": list_name.strip(), "entry": entry.strip()},
        )

    # -------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------

    def ping(self, *, timeout: float = 5.0) -> bool:
        """检查 YaCy 服务是否可达。

        通过调用 ``/api/version.json`` 来验证连接。

        Args:
            timeout: 超时时间（秒）。默认 5 秒。

        Returns:
            如果服务可达返回 True，否则返回 False。
        """
        try:
            self.version(timeout=timeout)
            return True
        except PYaCyError:
            return False

    def close(self) -> None:
        """关闭底层 HTTP 会话连接。

        在不再使用客户端时调用以释放网络资源。
        """
        self.session.close()
        _logger.info("YaCyClient 会话已关闭")

    def __enter__(self) -> "YaCyClient":
        """上下文管理器入口。

        支持 ``with YaCyClient(...) as client:`` 用法。
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口，自动关闭会话。"""
        self.close()
        return False

    def __repr__(self) -> str:
        return f"YaCyClient(base_url={self.base_url!r})"
