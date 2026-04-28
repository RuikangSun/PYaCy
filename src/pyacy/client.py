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
    - 零第三方依赖：仅使用 Python 标准库（urllib、http.client、json、ssl）
    - 不依赖 YaCy GPL 代码，纯基于公开 API 文档实现
"""

from __future__ import annotations

import json
import logging
import ssl
import time
import socket
from email.utils import formatdate
from io import BytesIO
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import (
    Request,
    urlopen,
    build_opener,
    HTTPSHandler,
    HTTPHandler,
    HTTPRedirectHandler,
    HTTPBasicAuthHandler,
    HTTPPasswordMgrWithDefaultRealm,
)

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

try:
    from importlib.metadata import version as _pkg_version
    _VERSION = _pkg_version("pyacy")
except Exception:
    _VERSION = "0.2.5"  # fallback：与 pyproject.toml 保持同步

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
# 内部工具：HTTP 响应包装
# ---------------------------------------------------------------------------


class _HttpResponse:
    """包装 urllib 的 HTTP 响应，提供与 requests.Response 兼容的接口。

    不直接暴露 urllib HTTPResponse 对象，而是解析后缓存关键属性。
    """

    def __init__(
        self,
        status_code: int,
        text: str,
        headers: dict[str, str],
    ):
        self.status_code = status_code
        self.text = text
        self.headers = headers

    def json(self) -> Any:
        """尝试将响应体解析为 JSON。

        Returns:
            解析后的 JSON 数据。

        Raises:
            ValueError: 如果响应体不是有效的 JSON。
        """
        return json.loads(self.text)


# ---------------------------------------------------------------------------
# 内部工具：multipart 构建
# ---------------------------------------------------------------------------


def _build_multipart_body(
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
    boundary: str,
) -> bytes:
    """构建 multipart/form-data 请求体。

    Args:
        fields: 普通表单字段，键为字段名，值为字段值。
        files: 文件字段，键为字段名，值为 ``(文件名, 内容, MIME类型)`` 元组。
        boundary: 分隔边界字符串。

    Returns:
        完整的 multipart 请求体字节串。
    """
    body_parts: list[bytes] = []

    def _add_line(line: str) -> None:
        body_parts.append(line.encode("utf-8"))

    def _add_bytes(data: bytes) -> None:
        body_parts.append(data)

    # 普通字段
    for name, value in fields.items():
        _add_line(f"--{boundary}")
        _add_line(f'Content-Disposition: form-data; name="{name}"')
        _add_line("")
        _add_line(value)

    # 文件字段
    for name, (filename, content, mime_type) in files.items():
        _add_line(f"--{boundary}")
        _add_line(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'
        )
        _add_line(f"Content-Type: {mime_type}")
        _add_line("")
        _add_bytes(content)

    # 结束边界
    _add_line(f"--{boundary}--")

    return b"\r\n".join(body_parts)


# ---------------------------------------------------------------------------
# 内部工具：重试循环
# ---------------------------------------------------------------------------


def _http_request_with_retry(
    method: str,
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    backoff_factor: float = _DEFAULT_BACKOFF_FACTOR,
    retry_codes: frozenset[int] = _RETRY_STATUS_CODES,
    opener: Any = None,
) -> _HttpResponse:
    """发送 HTTP 请求并自动重试可恢复的错误。

    此函数是 client.py 内部所有 HTTP 请求的底层通道。
    使用标准库 urllib，零第三方依赖。

    Args:
        method: HTTP 方法（GET / POST）。
        url: 完整请求 URL。
        data: 请求体（POST 时使用）。
        headers: 自定义请求头。
        timeout: 超时时间（秒）。
        max_retries: 最大重试次数。
        backoff_factor: 指数退避因子。
        retry_codes: 应触发重试的 HTTP 状态码集合。
        opener: urllib OpenerDirector（用于 SSL 配置和认证）。

    Returns:
        _HttpResponse: 解析后的响应对象。

    Raises:
        PYaCyTimeoutError: 请求超时。
        PYaCyConnectionError: 网络连接失败。
    """
    req_headers = headers.copy() if headers else {}

    if data is not None:
        req_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    request = Request(url, data=data, headers=req_headers, method=method)

    last_exception: Exception | None = None
    send_opener = opener or build_opener()

    for attempt in range(max_retries + 1):
        try:
            with send_opener.open(request, timeout=timeout) as resp:
                raw_body = resp.read()
                encoding = resp.headers.get_content_charset("utf-8") or "utf-8"
                text = raw_body.decode(encoding, errors="replace")
                status = resp.status
                resp_headers = dict(resp.headers)

            # 重试触发码 — 在下次循环重试
            if status in retry_codes and attempt < max_retries:
                _logger.debug(
                    "HTTP %d（可重试），第 %d/%d 次尝试，等待 %.1fs",
                    status, attempt + 1, max_retries + 1,
                    backoff_factor * (2 ** attempt),
                )
                time.sleep(backoff_factor * (2 ** attempt))
                continue

            return _HttpResponse(
                status_code=status,
                text=text,
                headers=resp_headers,
            )

        except socket.timeout as exc:
            last_exception = PYaCyTimeoutError(
                f"请求超时: {method} {url} (超时 {timeout}s)",
                timeout=timeout,
            )
            last_exception.__cause__ = exc
            if attempt < max_retries:
                _logger.debug("超时重试 %d/%d", attempt + 1, max_retries + 1)
                time.sleep(backoff_factor * (2 ** attempt))
                continue

        except (URLError, OSError) as exc:
            last_exception = PYaCyConnectionError(
                f"无法连接到 P2P 节点: {url}",
                original_error=exc,
            )
            if attempt < max_retries:
                _logger.debug("连接失败重试 %d/%d", attempt + 1, max_retries + 1)
                time.sleep(backoff_factor * (2 ** attempt))
                continue

        except Exception as exc:
            last_exception = PYaCyConnectionError(
                f"请求发生未知错误: {method} {url}",
                original_error=exc,
            )
            if attempt < max_retries:
                time.sleep(backoff_factor * (2 ** attempt))
                continue

    # 所有重试均失败
    assert last_exception is not None
    raise last_exception


# ---------------------------------------------------------------------------
# YaCyClient
# ---------------------------------------------------------------------------


class YaCyClient:
    """YaCy 搜索引擎 HTTP 客户端。

    封装了与 YaCy 节点交互的所有 HTTP 请求，
    提供类型安全的 API 访问方式。

    使用纯 Python 标准库（urllib），零第三方依赖。

    Attributes:
        base_url: YaCy 服务的基础 URL（如 ``http://localhost:8090``）。
        timeout: 默认请求超时时间（秒）。
        auth: (用户名, 密码) 元组，用于 HTTP Basic Auth。
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
        self.max_retries: int = max_retries
        self.verify_ssl: bool = verify_ssl

        # ---- 构建 opener（SSL 配置 + 认证） ----
        ssl_context = None if verify_ssl else ssl.create_default_context()
        if not verify_ssl:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        handlers: list[Any] = [
            HTTPHandler(),
            HTTPSHandler(context=ssl_context),
            HTTPRedirectHandler(),
        ]

        if auth:
            password_mgr = HTTPPasswordMgrWithDefaultRealm()
            password_mgr.add_password(None, url, auth[0], auth[1])
            handlers.append(HTTPBasicAuthHandler(password_mgr))

        self._opener = build_opener(*handlers)

        # ---- 默认请求头 ----
        self._default_headers: dict[str, str] = {
            "User-Agent": f"PYaCy/{_VERSION} (Python YaCy Client)",
            "Accept": "application/json, text/xml, */*",
        }

        _logger.debug("YaCyClient 初始化完成: base_url=%s, timeout=%.1fs", url, timeout)

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

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        timeout: float | None = None,
    ) -> _HttpResponse:
        """发送 HTTP 请求并处理通用错误。

        这是所有 API 调用的底层方法。

        Args:
            method: HTTP 方法（GET / POST）。
            path: API 路径（相对于 base_url）。
            params: URL 查询参数。
            data: POST 表单数据。
            files: 文件上传列表。
            timeout: 超时时间（秒），None 则使用实例默认值。

        Returns:
            ``_HttpResponse`` 对象。

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

        # 追加查询参数
        if cleaned_params:
            query_string = urlencode(cleaned_params, doseq=True)
            url = f"{url}?{query_string}"

        # 构建请求头
        req_headers = dict(self._default_headers)

        body: bytes | None = None
        if files:
            # multipart/form-data 模式
            boundary = f"----PYaCyBoundary{int(time.time() * 1000)}"
            req_headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            # data 混入 multipart
            multipart_fields: dict[str, str] = {}
            if data:
                multipart_fields = {k: str(v) for k, v in data.items()}
            body = _build_multipart_body(multipart_fields, files, boundary)
        elif data:
            # application/x-www-form-urlencoded
            body = urlencode(data, doseq=True).encode("utf-8")
            req_headers["Content-Type"] = "application/x-www-form-urlencoded"

        _logger.debug("%s %s", method, url)

        response = _http_request_with_retry(
            method=method,
            url=url,
            data=body,
            headers=req_headers,
            timeout=timeout_val,
            max_retries=self.max_retries,
            opener=self._opener,
        )

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

        try:
            return response.json()
        except ValueError as exc:
            raise PYaCyResponseError(
                f"无法解析 JSON 响应: {response.text[:300]}",
                status_code=response.status_code,
            ) from exc

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
            maximum_records: 返回的最大结果数。默认 10。
            start_record: 结果起始偏移量（0-based）。默认 0。
            content_dom: 内容类型过滤。可选值: ``"text"`` | ``"image"``
                | ``"audio"`` | ``"video"`` | ``"app"``。
            verify: 结果验证策略。
            url_mask_filter: URL 过滤正则表达式。
            prefer_mask_filter: URL 偏好正则。
            language: 语言代码过滤。
            navigators: 导航器显示选项。``"all"`` 显示所有。
            timeout: 本次请求的超时时间（秒）。

        Returns:
            SearchResponse: 包含搜索结果的结构化对象。

        Raises:
            PYaCyValidationError: 如果 query 为空。
            PYaCyConnectionError: 网络连接失败。
            PYaCyTimeoutError: 请求超时。
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
        """
        if not query or not query.strip():
            raise PYaCyValidationError("搜索建议关键词不能为空")

        data = self._get_json("/suggest.json", params={"query": query.strip()})
        if isinstance(data, list):
            return SuggestResponse.from_json(data)
        return SuggestResponse(raw=[data] if isinstance(data, dict) else [])

    # -------------------------------------------------------------------
    # 状态与信息 API
    # -------------------------------------------------------------------

    def status(self, *, timeout: float | None = None) -> PeerStatus:
        """获取 YaCy 节点的运行状态。

        对应 YaCy API ``/api/status_p.json``。

        Returns:
            PeerStatus: 节点状态信息。

        Example:
            >>> client = YaCyClient()
            >>> status = client.status()
            >>> print(f"索引文档数: {status.index_size}")
        """
        data = self._get_json("/api/status_p.json")
        return PeerStatus.from_json(data)

    def version(self, *, timeout: float | None = None) -> VersionInfo:
        """获取 YaCy 版本信息。

        对应 YaCy API ``/api/version.json``。

        Returns:
            VersionInfo: 版本、构建日期等信息。
        """
        data = self._get_json("/api/version.json")
        return VersionInfo.from_json(data)

    def network(self, *, timeout: float | None = None) -> NetworkInfo:
        """获取 YaCy P2P 网络统计信息。

        对应 YaCy API ``/Network.json``。

        Returns:
            NetworkInfo: 活跃节点数、总 URL 数等。
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
            start_url: 爬虫起始 URL。
            crawling_depth: 爬取深度。默认 1。
            must_match: URL 必须匹配的正则表达式。
            must_not_match: URL 不得匹配的正则表达式。
            index_text: 是否索引文本内容。默认 True。
            index_media: 是否索引媒体文件。默认 False。
            crawling_q: 爬虫入口选择。
            recrawl_cycle: 重新爬取周期。
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

        response = self._request("POST", "/Crawler_p.html", data=data)
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
        """以专家模式启动爬虫任务。

        对应 YaCy 的 ``/CrawlStartExpert.html`` 端点。

        Args:
            start_url: 爬虫起始 URL。
            crawling_depth: 爬取深度。默认 1。
            must_match: 必须匹配的正则。
            must_not_match: 不得匹配的正则。
            crawl_order: 爬取顺序。
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

        response = self._request("POST", "/CrawlStartExpert.html", data=data)
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

        Args:
            url: 文档的 URL。
            content: 文档内容（文本或二进制数据）。
            content_type: MIME 类型。默认 ``"text/html"``。
            collection: 集合名称。
            last_modified: 最后修改时间（RFC 1123 格式）。
            title: 媒体文档标题。
            keywords: 媒体关键词。
            commit: 是否立即提交索引。默认 False。
            synchronous: 是否同步处理。默认 False。
            timeout: 超时时间（秒）。

        Returns:
            PushResponse: 推送结果。

        Raises:
            PYaCyValidationError: 如果 url 为空。
        """
        if not url or not url.strip():
            raise PYaCyValidationError("文档 URL 不能为空")

        # 构建 multipart 数据
        data_fields: dict[str, str] = {
            "count": "1",
            "url-0": url.strip(),
            "synchronous": "true" if synchronous else "false",
            "commit": "true" if commit else "false",
        }
        if collection:
            data_fields["collection-0"] = collection

        # 响应头
        response_headers = [f"Content-Type:{content_type}"]
        if last_modified:
            response_headers.append(f"Last-Modified:{last_modified}")
        if title:
            response_headers.append(f"X-YaCy-Media-Title:{title}")
        if keywords:
            response_headers.append(f"X-YaCy-Media-Keywords:{keywords}")
        data_fields["responseHeader-0"] = ",".join(response_headers)

        # 内容转字节
        content_bytes = content if isinstance(content, bytes) else content.encode("utf-8")

        files_map = {"data-0": ("document", content_bytes, content_type)}

        response = self._request(
            "POST",
            "/api/push_p.json",
            data=data_fields,
            files=files_map,
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

        Args:
            documents: 文档列表，每个元素包含 ``url``、``content`` 等键。
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
        data_fields: dict[str, str] = {
            "count": str(count),
            "synchronous": "true" if synchronous else "false",
            "commit": "true" if commit else "false",
        }
        files_map: dict[str, tuple[str, bytes, str]] = {}

        for i, doc in enumerate(documents):
            url = doc.get("url", "")
            if not url:
                raise PYaCyValidationError(f"第 {i} 个文档缺少 url")

            data_fields[f"url-{i}"] = url

            content = doc.get("content", "")
            content_bytes = content if isinstance(content, bytes) else str(content).encode("utf-8")
            ct = doc.get("content_type", "text/html")
            files_map[f"data-{i}"] = (f"document-{i}", content_bytes, ct)

            if doc.get("collection"):
                data_fields[f"collection-{i}"] = doc["collection"]

            headers_list = [f"Content-Type:{ct}"]
            if doc.get("last_modified"):
                headers_list.append(f"Last-Modified:{doc['last_modified']}")
            if doc.get("title"):
                headers_list.append(f"X-YaCy-Media-Title:{doc['title']}")
            if doc.get("keywords"):
                headers_list.append(f"X-YaCy-Media-Keywords:{doc['keywords']}")
            data_fields[f"responseHeader-{i}"] = ",".join(headers_list)

        response = self._request(
            "POST",
            "/api/push_p.json",
            data=data_fields,
            files=files_map,
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

        Args:
            url: 要删除的文档 URL。
            host: 要删除的主机名下所有文档。
            delete_all: True 则清空整个索引（慎用！）。
            timeout: 超时时间（秒）。

        Returns:
            删除操作结果信息。

        Raises:
            PYaCyValidationError: 未指定删除目标。
        """
        if not delete_all and not url and not host:
            raise PYaCyValidationError(
                "必须指定至少一个删除目标: url、host 或 delete_all=True"
            )

        data: dict[str, str] = {}
        if delete_all:
            data["deleteall"] = "true"
        if url:
            data["url"] = url
        if host:
            data["host"] = host

        response = self._request("POST", "/IndexDeletion_p.html", data=data)
        return {
            "status_code": response.status_code,
            "message": "索引删除请求已提交",
        }

    # -------------------------------------------------------------------
    # 黑名单管理 API
    # -------------------------------------------------------------------

    def get_blacklists(self, *, timeout: float | None = None) -> dict[str, Any]:
        """获取所有黑名单的元数据列表。

        Returns:
            黑名单元数据字典。
        """
        return self._get_json("/api/blacklists/get_metadata_p.json")

    def get_blacklist(
        self, list_name: str, *, timeout: float | None = None
    ) -> dict[str, Any]:
        """获取指定黑名单的内容。

        Args:
            list_name: 黑名单名称。

        Returns:
            黑名单内容。

        Raises:
            PYaCyValidationError: 如果 list_name 为空。
        """
        if not list_name or not list_name.strip():
            raise PYaCyValidationError("黑名单名称不能为空")
        return self._get_json(
            "/api/blacklists/get_list_p.json",
            params={"list": list_name.strip()},
        )

    def add_blacklist_entry(
        self,
        list_name: str,
        entry: str,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """向黑名单添加条目。

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

        Args:
            timeout: 超时时间（秒）。默认 5 秒。

        Returns:
            True 表示可达，False 表示不可达。
        """
        try:
            self.version(timeout=timeout)
            return True
        except PYaCyError:
            return False

    def close(self) -> None:
        """释放网络资源。

        urllib 下连接为无状态，此方法主要用于与上下文管理器兼容。
        """
        _logger.debug("YaCyClient 会话已关闭")

    def __enter__(self) -> "YaCyClient":
        """上下文管理器入口。"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口。"""
        self.close()
        return False

    def __repr__(self) -> str:
        return f"YaCyClient(base_url={self.base_url!r})"
