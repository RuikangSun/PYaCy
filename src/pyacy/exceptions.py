# -*- coding: utf-8 -*-
"""PYaCy 自定义异常类。

本模块定义了 PYaCy 客户端库使用的所有自定义异常，
便于调用方精确捕获和处理不同类型的错误。

异常层次结构::

    PYaCyError              (基类)
    ├── PYaCyConnectionError (网络连接失败)
    ├── PYaCyTimeoutError    (请求超时)
    ├── PYaCyResponseError   (API 返回错误)
    │   ├── PYaCyAuthError   (认证失败)
    │   └── PYaCyServerError (服务端内部错误)
    └── PYaCyValidationError (参数校验失败)
"""


class PYaCyError(Exception):
    """PYaCy 客户端库所有异常的基类。

    所有自定义异常均继承自此异常，调用方可以捕获
    ``PYaCyError`` 来统一处理本库抛出的所有错误。
    """
    pass


class PYaCyConnectionError(PYaCyError):
    """与 YaCy 服务器建立网络连接失败时抛出。

    可能原因：
        - YaCy 服务未启动
        - 主机地址或端口配置错误
        - 网络不可达
        - DNS 解析失败
    """

    def __init__(self, message: str, original_error: Exception | None = None):
        """初始化连接异常。

        Args:
            message: 错误描述信息。
            original_error: 原始异常对象，用于调试（可选）。
        """
        super().__init__(message)
        self.original_error = original_error


class PYaCyTimeoutError(PYaCyError):
    """请求超时时抛出。

    可能原因：
        - 网络延迟过高
        - YaCy 服务负载过大
        - 请求的数据量过大
    """

    def __init__(self, message: str, timeout: float | None = None):
        """初始化超时异常。

        Args:
            message: 错误描述信息。
            timeout: 超时时间（秒）。
        """
        super().__init__(message)
        self.timeout = timeout


class PYaCyResponseError(PYaCyError):
    """YaCy API 返回非成功状态码时抛出。

    这是 API 响应错误的基类，包含 HTTP 状态码和响应内容
    等调试信息。
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ):
        """初始化响应异常。

        Args:
            message: 错误描述信息。
            status_code: HTTP 状态码。
            response_body: 响应体内容。
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class PYaCyAuthError(PYaCyResponseError):
    """认证失败（HTTP 401/403）时抛出。

    可能原因：
        - 未配置认证凭据
        - 用户名或密码错误
        - API 密钥无效
    """
    pass


class PYaCyServerError(PYaCyResponseError):
    """YaCy 服务端返回 5xx 错误时抛出。

    这通常表示 YaCy 服务内部出现问题，可能需要查看
    服务端日志来定位具体原因。
    """
    pass


class PYaCyValidationError(PYaCyError):
    """客户端参数校验失败时抛出。

    在发送请求之前对参数进行本地校验，如果参数不合法
    则抛出此异常，避免无效请求发送到服务端。
    """
    pass
