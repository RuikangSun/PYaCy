# -*- coding: utf-8 -*-
"""PYaCy P2P 协议编码模块。

本模块实现了 YaCy P2P 通信所需的 HTTP 多部分表单编码。
所有 P2P 端点（hello, search, transferRWI 等）都使用 multipart/form-data 格式。

设计原则:
    - 纯 Python 标准库实现（使用 http.client）
    - 不依赖 requests 等第三方库
    - 与 YaCy Java 的 multipart POST 完全兼容
"""

from __future__ import annotations

import io
import logging
import time
import uuid
from http.client import HTTPConnection, HTTPResponse, HTTPSConnection
from typing import Any
from urllib.parse import urlparse

from ..exceptions import (
    PYaCyConnectionError,
    PYaCyP2PError,
    PYaCyTimeoutError,
)
from ..utils import random_salt

#: 日志记录器
_logger = logging.getLogger(__name__)

#: 默认请求超时（秒）
DEFAULT_TIMEOUT: int = 30

#: 网络名称（YaCy 默认）
DEFAULT_NETWORK_NAME: str = "freeworld"

try:
    from importlib.metadata import version as _pkg_version
    _VERSION = _pkg_version("pyacy")
except Exception:
    _VERSION = "0.2.5"  # fallback：与 pyproject.toml 保持同步


class P2PResponse:
    """P2P 请求的解析响应。

    YaCy P2P 响应是 key=value 格式的纯文本，每行一对。
    """

    def __init__(self, raw_text: str):
        """解析 P2P 响应文本。

        Args:
            raw_text: 原始响应文本。
        """
        self.raw: str = raw_text
        self.data: dict[str, str] = {}
        self._parse()

    def _parse(self) -> None:
        """解析 key=value 行。

        第一行若不包含 ``=``，视为状态行存入 ``data["__status__"]``。
        例如 YaCy 某些端点返回 ``ok 263`` 作为首行状态码。
        """
        first = True
        for line in self.raw.splitlines():
            line = line.strip()
            if not line:
                continue
            eq_pos = line.find("=")
            if eq_pos > 0:
                key = line[:eq_pos].strip()
                value = line[eq_pos + 1:]
                self.data[key] = value
            elif first and eq_pos == -1:
                # 第一行没有 "=" — 视为状态行
                self.data["__status__"] = line
                self.data["message"] = line
            first = False

    def get(self, key: str, default: str = "") -> str:
        """获取响应字段值。

        Args:
            key: 字段键名。
            default: 默认值。

        Returns:
            字段值。
        """
        return self.data.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        """获取整型响应字段。

        Args:
            key: 字段键名。
            default: 默认值。

        Returns:
            整型值。
        """
        try:
            return int(self.data.get(key, ""))
        except (ValueError, TypeError):
            return default

    def __repr__(self) -> str:
        return f"P2PResponse({len(self.data)} fields)"


class P2PProtocol:
    """YaCy P2P HTTP 协议客户端。

    负责构建和发送 multipart/form-data 请求到 YaCy P2P 端点，
    并解析 key=value 格式的响应。

    使用示例::

        protocol = P2PProtocol()
        response = protocol.hello(target_url="http://peer:8090", ...)
    """

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def __init__(
        self,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        network_name: str = DEFAULT_NETWORK_NAME,
    ):
        """初始化 P2P 协议客户端。

        Args:
            timeout: HTTP 请求超时（秒）。
            network_name: YaCy 网络名称（默认 "freeworld"）。
        """
        self.timeout: int = timeout
        self.network_name: str = network_name

    # ------------------------------------------------------------------
    # 核心：发送 multipart POST 请求
    # ------------------------------------------------------------------

    def post_multipart(
        self,
        url: str,
        parts: dict[str, str],
        *,
        hex_hash: str | None = None,
        timeout: int | None = None,
    ) -> P2PResponse:
        """发送 multipart/form-data POST 请求到 YaCy P2P 端点。

        YaCy 特有的认证方式：在 URL 后附加 ``<hexHash>.yacyh`` 作为
        HTTP Basic Auth 的用户名（密码为空）。

        Args:
            url: 完整的目标 URL（如 ``http://peer:8090/yacy/hello.html``）。
            parts: 要发送的表单字段。
            hex_hash: 目标节点的十六进制哈希（用于认证）。
            timeout: 超时时间（秒），默认使用实例配置。

        Returns:
            解析后的 P2P 响应。

        Raises:
            PYaCyConnectionError: 连接失败。
            PYaCyTimeoutError: 请求超时。
            PYaCyP2PError: P2P 协议错误。
        """
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8090
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        timeout_val = timeout if timeout is not None else self.timeout

        # 构建 multipart 请求体
        boundary = _generate_boundary()
        body = _encode_multipart(parts, boundary)

        # 构建请求头
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
            "User-Agent": f"PYaCy/{_VERSION} (Python YaCy P2P Client)",
            "Accept": "*/*",
            "Connection": "close",
        }

        # 添加 YaCy 专有认证头
        actual_path = path
        if hex_hash:
            auth_value = f"{hex_hash}.yacyh"
            headers["Authorization"] = f"Basic {_encode_basic_auth(auth_value, '')}"
            # YaCy 也将 hash 附加到 URL 路径
            actual_path = f"{path}?{hex_hash}.yacyh" if "?" in path else f"{path}?{hex_hash}.yacyh"

        _logger.debug("P2P POST %s:%d%s (parts=%d)", host, port, actual_path, len(parts))

        try:
            if parsed.scheme == "https":
                conn = HTTPSConnection(host, port, timeout=timeout_val)
            else:
                conn = HTTPConnection(host, port, timeout=timeout_val)

            conn.request("POST", actual_path, body=body, headers=headers)
            response = conn.getresponse()
            raw_text = response.read().decode("utf-8", errors="replace")
            conn.close()

            _logger.debug("P2P response: status=%d, body=%d bytes", response.status, len(raw_text))

            if response.status >= 400:
                raise PYaCyP2PError(
                    f"P2P 请求失败 (HTTP {response.status}): {raw_text[:200]}",
                    status_code=response.status,
                )

            return P2PResponse(raw_text)

        except (ConnectionRefusedError, ConnectionError, OSError) as exc:
            raise PYaCyConnectionError(
                f"无法连接到 P2P 节点: {host}:{port}",
                original_error=exc,
            ) from exc
        except TimeoutError as exc:
            raise PYaCyTimeoutError(
                f"P2P 请求超时: {url} (超时 {timeout_val}s)",
                timeout=timeout_val,
            ) from exc
        except PYaCyP2PError:
            raise
        except Exception as exc:
            raise PYaCyP2PError(
                f"P2P 请求异常: {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # 构建基本请求参数
    # ------------------------------------------------------------------

    def basic_request_parts(
        self,
        my_hash: str,
        *,
        target_hash: str | None = None,
        salt: str | None = None,
    ) -> dict[str, str]:
        """构建 YaCy P2P 请求的基本字段。

        所有 P2P 请求都需要包含这些基本身份信息。

        Args:
            my_hash: 本地节点的哈希值。
            target_hash: 目标节点的哈希值（可选）。
            salt: 会话密钥（可选，自动生成）。

        Returns:
            基本请求字段字典。
        """
        if salt is None:
            salt = random_salt()

        now_ms = int(time.time() * 1000)
        now_formatted = time.strftime("%Y/%m/%d %H:%M:%S", time.localtime())

        parts: dict[str, str] = {
            "iam": my_hash,
            "key": salt,
            "mytime": now_formatted,
            "myUTC": str(now_ms),
            "network.unit.name": self.network_name,
        }

        if target_hash:
            parts["youare"] = target_hash

        return parts

    # ------------------------------------------------------------------
    # 高层 P2P 操作
    # ------------------------------------------------------------------

    def hello(
        self,
        target_url: str,
        target_hash: str,
        my_seed_str: str,
        my_hash: str,
        count: int = 20,
        magic: int = 0,
    ) -> P2PResponse:
        """向远程节点发送 Hello 请求。

        Hello 是 YaCy P2P 的核心握手协议，用于：
        1. 宣告自身存在
        2. 获取对方对自己的节点类型判定
        3. 发现更多节点

        Args:
            target_url: 目标节点的 URL（如 ``http://peer:8090``）。
            target_hash: 目标节点的哈希值。
            my_seed_str: 自己节点的种子字符串。
            my_hash: 自己节点的哈希值。
            count: 请求返回的种子数量（默认 20）。
            magic: 网络魔数（用于网络隔离，默认 0 表示 freeworld）。

        Returns:
            Hello 响应。
        """
        salt = random_salt()
        parts = self.basic_request_parts(my_hash, target_hash=target_hash, salt=salt)
        parts["count"] = str(count)
        parts["magic"] = str(magic)
        parts["seed"] = my_seed_str

        hex_hash = target_hash  # YaCy 认证使用十六进制哈希
        # 构建完整 URL
        hello_url = f"{target_url.rstrip('/')}/yacy/hello.html"

        return self.post_multipart(hello_url, parts, hex_hash=hex_hash)

    def search(
        self,
        target_url: str,
        target_hash: str,
        my_hash: str,
        query_hashes: str,
        *,
        my_seed_str: str | None = None,
        count: int = 10,
        max_time: int = 3000,
        max_dist: int = 3,
        language: str = "",
        prefer: str = "",
        contentdom: str = "all",
        exclude_hashes: str = "",
        url_hashes: str = "",
        abstracts: str = "auto",
        partitions: int = 30,
        filter_regex: str = ".*",
    ) -> P2PResponse:
        """在远程节点上执行 DHT 搜索。

        向远程节点发送词哈希查询，获取匹配的 URL 引用结果。

        Args:
            target_url: 目标节点 URL。
            target_hash: 目标节点哈希。
            my_hash: 本地节点哈希。
            query_hashes: 搜索词哈希字符串（多个词哈希直接拼接）。
            my_seed_str: 本地种子字符串（可选）。
            count: 期望结果数（默认 10）。
            max_time: 最大等待时间（毫秒，默认 3000）。
            max_dist: 最大跳数（默认 3）。
            language: 语言过滤（如 "zh", "en"）。
            prefer: 偏好排序方式。
            contentdom: 内容域过滤（默认 "all"）。
            exclude_hashes: 排除词哈希。
            url_hashes: 预选 URL 哈希。
            abstracts: 摘要生成方式（"auto"/"true"/""）。
            partitions: 索引分区数（默认 30）。
            filter_regex: URL 过滤正则（默认 ".*"）。

        Returns:
            搜索响应。
        """
        salt = random_salt()
        parts = self.basic_request_parts(my_hash, target_hash=target_hash, salt=salt)
        parts["query"] = query_hashes
        parts["count"] = str(count)
        parts["time"] = str(max_time)
        parts["maxdist"] = str(max_dist)
        parts["contentdom"] = contentdom
        parts["abstracts"] = abstracts
        parts["partitions"] = str(partitions)
        parts["filter"] = filter_regex

        if exclude_hashes:
            parts["exclude"] = exclude_hashes
        if url_hashes:
            parts["urls"] = url_hashes
        if language:
            parts["language"] = language
        if prefer:
            parts["prefer"] = prefer
        if my_seed_str:
            parts["myseed"] = my_seed_str

        hex_hash = target_hash
        search_url = f"{target_url.rstrip('/')}/yacy/search.html"

        return self.post_multipart(search_url, parts, hex_hash=hex_hash)

    def seedlist(self, target_url: str) -> P2PResponse | list[dict[str, Any]]:
        """获取节点的种子列表（Bootstrap）。

        支持 JSON 格式（优先）和 HTML 格式。

        Args:
            target_url: 目标节点 URL。

        Returns:
            种子响应（JSON 格式时返回列表，HTML 格式时返回 P2PResponse）。
        """
        import json as _json
        from urllib.request import Request, urlopen

        # 优先尝试 JSON
        json_url = f"{target_url.rstrip('/')}/yacy/seedlist.json"
        try:
            req = Request(json_url, headers={"User-Agent": f"PYaCy/{_VERSION}"})
            with urlopen(req, timeout=self.timeout) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            return data
        except Exception:
            _logger.debug("seedlist.json 不可用，回退到 HTML")
            html_url = f"{target_url.rstrip('/')}/yacy/seedlist.html"
            return self.post_multipart(html_url, {})


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------


def _generate_boundary() -> str:
    """生成唯一的 multipart 边界字符串。

    Returns:
        边界字符串。
    """
    return f"--PYaCy-{uuid.uuid4().hex}"


def _encode_multipart(parts: dict[str, str], boundary: str) -> bytes:
    """将字段字典编码为 multipart/form-data 字节流。

    Args:
        parts: 表单字段字典。
        boundary: 边界字符串。

    Returns:
        multipart 编码后的字节流。
    """
    buffer = io.BytesIO()
    boundary_bytes = boundary.encode("ascii")
    crlf = b"\r\n"

    for key, value in parts.items():
        buffer.write(b"--" + boundary_bytes + crlf)
        header = (
            f'Content-Disposition: form-data; name="{key}"\r\n'
            f"Content-Type: text/plain; charset=UTF-8\r\n"
            f"\r\n"
        )
        buffer.write(header.encode("utf-8"))
        buffer.write(value.encode("utf-8"))
        buffer.write(crlf)

    # 结束边界
    buffer.write(b"--" + boundary_bytes + b"--" + crlf)

    return buffer.getvalue()


def _encode_basic_auth(username: str, password: str) -> str:
    """编码 HTTP Basic Auth 凭据。

    Args:
        username: 用户名。
        password: 密码。

    Returns:
        Base64 编码的凭据字符串。
    """
    import base64
    creds = f"{username}:{password}".encode("utf-8")
    return base64.b64encode(creds).decode("ascii")
