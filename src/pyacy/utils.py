# -*- coding: utf-8 -*-
"""PYaCy 工具函数模块。

本模块提供 P2P 协议所需的底层工具函数，包括：
- YaCy 专有 Base64 编解码
- 词哈希计算（MD5 → YaCy Base64）
- 种子字符串解析与生成
- 随机盐生成

所有函数均基于 Python 标准库实现，零外部依赖。
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import os
import re
from typing import Any


# ---------------------------------------------------------------------------
# YaCy 专有 Base64 字符表
# ---------------------------------------------------------------------------

#: YaCy 使用的自定义 Base64 字符表（与标准 Base64 不同）。
#: 大小写字母在前，数字在后，最后两个字符是 ``-`` 和 ``_``。
YACY_BASE64_ALPHABET: str = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789-_"
)

#: 反向映射：字符 → 索引
_YACY_BASE64_DECODE: dict[str, int] = {
    c: i for i, c in enumerate(YACY_BASE64_ALPHABET)
}

#: 词哈希的标准长度（前 12 个 Base64 字符 = 72 bits of MD5）
WORD_HASH_LENGTH: int = 12


# ---------------------------------------------------------------------------
# 词哈希
# ---------------------------------------------------------------------------


def word_to_hash(word: str) -> str:
    """将搜索词转换为 YaCy 词哈希。

    YaCy 使用 MD5 的前 72 bits（12 个 Base64 字符）作为词哈希。
    计算过程：
    1. 词转小写 → UTF-8 编码 → MD5 → 16 字节
    2. 取前 9 字节（72 bits）→ 按 6 bits 分组 → YaCy Base64 编码 → 12 字符

    Args:
        word: 待哈希的搜索词。

    Returns:
        12 字符的 YaCy 词哈希字符串。
    """
    md5_bytes = hashlib.md5(word.lower().encode("utf-8")).digest()
    # 取前 9 字节（72 bits），编码为 12 个 Base64 字符（72/6=12）
    return _bytes_to_yacy_base64(md5_bytes[:9], WORD_HASH_LENGTH)


def words_to_hash_query(words: list[str]) -> str:
    """将多个搜索词拼接为 DHT 查询字符串。

    多个词哈希直接拼接。
    例如: ``words_to_hash_query(["hello", "world"])`` → ``"abcDEFghiJKLxyz123stuVWX"``

    Args:
        words: 搜索词列表。

    Returns:
        拼接后的词哈希字符串。
    """
    return "".join(word_to_hash(w) for w in words)


def hash_to_words_exclude(words: list[str]) -> str:
    """将排除词转换为排除哈希字符串。

    Args:
        words: 要排除的搜索词列表。

    Returns:
        拼接后的排除哈希字符串。
    """
    return "".join(word_to_hash(w) for w in words)


# ---------------------------------------------------------------------------
# YaCy Base64 编解码
# ---------------------------------------------------------------------------


def _bytes_to_yacy_base64(data: bytes, target_length: int | None = None) -> str:
    """将字节数据编码为 YaCy 专有 Base64。

    编码规则：
    - 将字节流按 6 bits 分组
    - 每组映射到 YACY_BASE64_ALPHABET 中的一个字符

    Args:
        data: 原始字节数据。
        target_length: 目标字符数。若指定且编码结果更短，用 ``A`` 填充。
            若编码结果更长，截断到目标长度。

    Returns:
        YaCy Base64 编码字符串。
    """
    result: list[str] = []
    buffer: int = 0
    bits_in_buffer: int = 0

    for byte in data:
        buffer = (buffer << 8) | byte
        bits_in_buffer += 8
        while bits_in_buffer >= 6:
            bits_in_buffer -= 6
            index = (buffer >> bits_in_buffer) & 0x3F
            result.append(YACY_BASE64_ALPHABET[index])

    # 处理剩余位
    if bits_in_buffer > 0:
        index = (buffer << (6 - bits_in_buffer)) & 0x3F
        result.append(YACY_BASE64_ALPHABET[index])

    encoded = "".join(result)

    if target_length is not None:
        if len(encoded) < target_length:
            encoded += "A" * (target_length - len(encoded))
        elif len(encoded) > target_length:
            encoded = encoded[:target_length]

    return encoded


def yacy_base64_decode(encoded: str) -> bytes:
    """将 YaCy Base64 字符串解码为原始字节。

    Args:
        encoded: YaCy Base64 编码的字符串。

    Returns:
        解码后的原始字节。

    Raises:
        ValueError: 如果字符串包含非法字符。
    """
    result: bytearray = bytearray()
    buffer: int = 0
    bits_in_buffer: int = 0

    for ch in encoded:
        if ch not in _YACY_BASE64_DECODE:
            raise ValueError(f"非法 YaCy Base64 字符: {ch!r}")
        buffer = (buffer << 6) | _YACY_BASE64_DECODE[ch]
        bits_in_buffer += 6
        if bits_in_buffer >= 8:
            bits_in_buffer -= 8
            result.append((buffer >> bits_in_buffer) & 0xFF)

    return bytes(result)


# ---------------------------------------------------------------------------
# DHT 距离计算
# ---------------------------------------------------------------------------


def dht_distance(hash_a: str, hash_b: str) -> int:
    """计算两个 YaCy Base64 哈希之间的 XOR 距离。

    这是 DHT 哈希路由的核心度量函数。YaCy P2P 网络使用 XOR 距离
    来确定某个词哈希应该由哪个（哪些）节点负责存储和查询。

    算法:
        1. 将两个 YaCy Base64 哈希解码为原始字节
        2. 逐字节计算 XOR
        3. 将结果解释为整数距离

    Args:
        hash_a: 第一个 YaCy Base64 哈希（12 字符）。
        hash_b: 第二个 YaCy Base64 哈希（12 字符）。

    Returns:
        XOR 距离（非负整数）。距离越小表示两个哈希越接近。

    Raises:
        ValueError: 如果哈希字符串包含非法字符。

    示例::

        >>> dht_distance("AAAAAAAAAAAA", "AAAAAAAAAAAB")
        1
        >>> dht_distance("AAAAAAAAAAAA", "BAAAAAAAAAAA")
        4611686018427387904  # 2^62
    """
    raw_a = yacy_base64_decode(hash_a)
    raw_b = yacy_base64_decode(hash_b)

    distance = 0
    for a, b in zip(raw_a, raw_b):
        distance = (distance << 8) | (a ^ b)

    # 如果字节数不同，剩余字节直接附加
    if len(raw_a) > len(raw_b):
        for a in raw_a[len(raw_b):]:
            distance = (distance << 8) | a
    elif len(raw_b) > len(raw_a):
        for b in raw_b[len(raw_a):]:
            distance = (distance << 8) | b

    return distance


# ---------------------------------------------------------------------------
# 种子字符串
# ---------------------------------------------------------------------------


def decode_seed_string(seed_str: str) -> dict[str, str]:
    """解码 YaCy 种子字符串。

    支持两种格式：
    - **简单格式**: ``p|{Key1=Value1,Key2=Value2,...}``
    - **压缩格式**: ``z|H4sIA...``（Base64 of gzip）

    Args:
        seed_str: YaCy 种子字符串。

    Returns:
        种子属性字典。

    Raises:
        ValueError: 格式无法识别。
    """
    if not seed_str or len(seed_str) < 2:
        raise ValueError(f"种子字符串太短: {seed_str!r}")

    prefix = seed_str[0]
    separator_pos = seed_str.find("|")
    if separator_pos < 1:
        raise ValueError(f"无法解析种子字符串（缺少分隔符 '|'）: {seed_str[:50]!r}")

    body = seed_str[separator_pos + 1:]

    if prefix == "p":
        # 简单格式: p|{...}
        return _parse_seed_properties(body)
    elif prefix == "z":
        # 压缩格式: z|...(base64 of gzip)
        return _parse_compressed_seed(body)
    else:
        raise ValueError(f"未知种子前缀: {prefix!r}")


def encode_seed_string(dna: dict[str, str], *, compress: bool = True) -> str:
    """将属性字典编码为 YaCy 种子字符串。

    Args:
        dna: 种子属性字典。
        compress: 是否使用 gzip 压缩。默认 True。

    Returns:
        编码后的种子字符串。
    """
    props_str = _format_seed_properties(dna)

    if compress:
        compressed = gzip.compress(props_str.encode("utf-8"), compresslevel=9)
        b64 = base64.b64encode(compressed).decode("ascii")
        return f"z|{b64}"
    else:
        return f"p|{{{props_str}}}"


def _parse_seed_properties(body: str) -> dict[str, str]:
    """解析 ``{Key=Value,Key=Value}`` 格式的属性字符串。

    Args:
        body: 花括号内的属性字符串。

    Returns:
        属性字典。
    """
    # 去除花括号
    inner = body.strip()
    if inner.startswith("{") and inner.endswith("}"):
        inner = inner[1:-1]

    result: dict[str, str] = {}
    # 逗号分隔，但值中可能包含转义
    parts = _split_csv_properties(inner)
    for part in parts:
        eq_pos = part.find("=")
        if eq_pos > 0:
            key = part[:eq_pos].strip()
            value = _unescape_seed_value(part[eq_pos + 1:])
            result[key] = value

    return result


def _format_seed_properties(dna: dict[str, str]) -> str:
    """将属性字典格式化为 ``Key=Value,Key=Value`` 字符串。

    Args:
        dna: 属性字典。

    Returns:
        格式化的属性字符串。
    """
    parts = []
    for key, value in dna.items():
        escaped = _escape_seed_value(value)
        parts.append(f"{key}={escaped}")
    return ",".join(parts)


def _parse_compressed_seed(body: str) -> dict[str, str]:
    """解析压缩的种子字符串（Base64 of gzip）。

    Args:
        body: Base64 编码的 gzip 数据。

    Returns:
        属性字典。
    """
    try:
        compressed = base64.b64decode(body)
        decompressed = gzip.decompress(compressed)
        text = decompressed.decode("utf-8")
        return _parse_seed_properties(text)
    except Exception as e:
        raise ValueError(f"解压缩种子失败: {e}") from e


def _split_csv_properties(text: str) -> list[str]:
    """在属性字符串中安全地按逗号分割，处理逗号和反斜杠转义。

    YaCy 种子格式中:
    - ``\,`` 表示字面逗号
    - ``\\`` 表示字面反斜杠

    Args:
        text: CSV 风格的属性字符串。

    Returns:
        分割后的属性片段列表。
    """
    result: list[str] = []
    current: list[str] = []
    i = 0

    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            current.append(text[i + 1])
            i += 2
        elif ch == ",":
            result.append("".join(current))
            current = []
            i += 1
        elif ch in ("{", "}"):
            # 忽略花括号
            i += 1
        else:
            current.append(ch)
            i += 1

    if current:
        result.append("".join(current))

    return result


def _escape_seed_value(value: str) -> str:
    """转义种子值中的特殊字符。

    Args:
        value: 原始值。

    Returns:
        转义后的值。
    """
    return value.replace("\\", "\\\\").replace(",", "\\,")


def _unescape_seed_value(value: str) -> str:
    """反转义种子值。

    Args:
        value: 转义后的值。

    Returns:
        原始值。
    """
    return value.replace("\\,", ",").replace("\\\\", "\\")


# ---------------------------------------------------------------------------
# 随机工具
# ---------------------------------------------------------------------------


def random_salt(length: int = 16) -> str:
    """生成随机盐（用于 P2P 会话密钥）。

    Args:
        length: 盐的字符长度。默认 16。

    Returns:
        十六进制随机字符串。
    """
    return os.urandom(length).hex()[:length]


# ---------------------------------------------------------------------------
# 哈希工具
# ---------------------------------------------------------------------------


def b64hash_to_hex(b64hash: str) -> str:
    """将 YaCy Base64 哈希转换为十六进制。

    在某些 P2P 端点中，URL 包含 ``<hexhash>.yacyh`` 格式的认证字符串。

    Args:
        b64hash: YaCy Base64 哈希。

    Returns:
        十六进制字符串。
    """
    raw = yacy_base64_decode(b64hash)
    return raw.hex()


def hex_to_b64hash(hexhash: str) -> str:
    """将十六进制哈希转换为 YaCy Base64。

    Args:
        hexhash: 十六进制字符串。

    Returns:
        YaCy Base64 字符串。
    """
    raw = bytes.fromhex(hexhash)
    return _bytes_to_yacy_base64(raw)


def compute_peer_hash(identity: str) -> str:
    """根据身份字符串计算节点哈希。

    使用 SHA-256 并转换为 YaCy Base64（取 12 字符）。

    Args:
        identity: 节点身份标识字符串。

    Returns:
        12 字符 YaCy Base64 哈希。
    """
    sha = hashlib.sha256(identity.encode("utf-8")).digest()
    return _bytes_to_yacy_base64(sha[:9], WORD_HASH_LENGTH)


# ---------------------------------------------------------------------------
# YaCy SimpleCoding 编解码
# ---------------------------------------------------------------------------


def simplecoding_decode(value: str) -> str:
    """解码 YaCy SimpleCoding 格式的值。

    YaCy 在搜索响应等处使用 SimpleCoding 格式传输数据：
    - ``b|base64_data`` — Base64 编码的数据（需解码为 UTF-8 字符串）
    - ``p|plain_text`` — 明文数据（直接返回管道后的部分）
    - ``plain_text`` — 无前缀时视为纯文本（直接返回）

    Args:
        value: SimpleCoding 编码的字符串。

    Returns:
        解码后的字符串。

    示例::

        >>> simplecoding_decode("b|aGVsbG8=")
        "hello"
        >>> simplecoding_decode("p|world")
        "world"
        >>> simplecoding_decode("plain")
        "plain"
    """
    if not value:
        return ""

    pipe_pos = value.find("|")
    if pipe_pos < 0:
        # 无管道符：视为纯文本
        return value

    prefix = value[:pipe_pos].lower()
    data = value[pipe_pos + 1:]

    if prefix == "b":
        # Base64 编码
        try:
            # 使用标准 Base64 解码
            import base64 as _b64
            decoded = _b64.b64decode(data)
            return decoded.decode("utf-8", errors="replace")
        except Exception:
            # 解码失败时返回原始数据
            return data
    elif prefix == "p":
        # 明文
        return data
    else:
        # 未知前缀：返回完整原始值
        return value


def simplecoding_decode_bytes(value: str) -> bytes:
    """解码 YaCy SimpleCoding 值为原始字节。

    与 ``simplecoding_decode`` 的区别：此函数返回 bytes 而非 str，
    适用于需要原始二进制数据的场景。

    Args:
        value: SimpleCoding 编码的字符串。

    Returns:
        解码后的字节数据。
    """
    if not value:
        return b""

    pipe_pos = value.find("|")
    if pipe_pos < 0:
        return value.encode("utf-8")

    prefix = value[:pipe_pos].lower()
    data = value[pipe_pos + 1:]

    if prefix == "b":
        try:
            import base64 as _b64
            return _b64.b64decode(data)
        except Exception:
            return data.encode("utf-8")
    elif prefix == "p":
        return data.encode("utf-8")
    else:
        return value.encode("utf-8")


def parse_search_resource(resource_str: str) -> dict[str, str]:
    """解析 YaCy 搜索响应中的 resource 字段。

    resource 字段格式为：
    ``{hash=url_hash,url=b|base64_url,descr=b|base64_descr,...}``

    其中值使用 SimpleCoding 编码（``b|`` 或 ``p|`` 前缀）。

    Args:
        resource_str: resource 字段值（花括号包裹）。

    Returns:
        解析后的属性字典，值已解码。

    示例::

        >>> parse_search_resource("{hash=abc123,url=b|aHR0cDovL2V4YW1wbGUuY29t}")
        {"hash": "abc123", "url": "http://example.com"}
    """
    result: dict[str, str] = {}

    if not resource_str:
        return result

    # 去除花括号
    inner = resource_str.strip()
    if inner.startswith("{") and inner.endswith("}"):
        inner = inner[1:-1]

    if not inner:
        return result

    # 按逗号分割键值对
    # 注意：值中可能包含逗号（如 URL 参数），但 YaCy 使用反斜杠转义
    pairs = _split_csv_properties(inner)

    for pair in pairs:
        eq_pos = pair.find("=")
        if eq_pos < 0:
            continue
        key = pair[:eq_pos].strip()
        raw_value = pair[eq_pos + 1:]
        # 解码 SimpleCoding 值
        decoded_value = simplecoding_decode(raw_value)
        result[key] = decoded_value

    return result
