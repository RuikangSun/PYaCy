# -*- coding: utf-8 -*-
"""PYaCy 工具函数测试。

测试 utils.py 中的所有工具函数：
- YaCy Base64 编解码
- 词哈希计算
- 种子字符串解析与生成
"""

import gzip
import hashlib
from base64 import b64encode

import pytest

from pyacy.utils import (
    WORD_HASH_LENGTH,
    YACY_BASE64_ALPHABET,
    _bytes_to_yacy_base64,
    b64hash_to_hex,
    compute_peer_hash,
    decode_seed_string,
    encode_seed_string,
    hash_to_words_exclude,
    hex_to_b64hash,
    random_salt,
    word_to_hash,
    words_to_hash_query,
    yacy_base64_decode,
)


# ===================================================================
# YaCy Base64 编解码
# ===================================================================


class TestYacyBase64:
    """YaCy 专有 Base64 编解码测试。"""

    def test_alphabet_is_64_chars(self) -> None:
        """验证字符表恰好 64 个字符。"""
        assert len(YACY_BASE64_ALPHABET) == 64

    def test_alphabet_has_no_duplicates(self) -> None:
        """验证字符表无重复。"""
        assert len(set(YACY_BASE64_ALPHABET)) == 64

    def test_encode_single_byte(self) -> None:
        """单字节编码。"""
        # 0x00 → 前 6 位 + 填充
        result = _bytes_to_yacy_base64(b"\x00", target_length=2)
        assert len(result) == 2
        assert result == "AA"

    def test_encode_zero(self) -> None:
        """全零字节编码应全为 A。"""
        result = _bytes_to_yacy_base64(b"\x00\x00\x00")
        assert all(c == "A" for c in result)

    def test_encode_all_ones(self) -> None:
        """全 1 字节编码应全为 _（索引 63）。"""
        result = _bytes_to_yacy_base64(b"\xff\xff\xff", target_length=4)
        assert all(c == "_" for c in result)

    def test_roundtrip(self) -> None:
        """编解码往返测试。"""
        original = b"Hello, YaCy P2P!"
        encoded = _bytes_to_yacy_base64(original)
        decoded = yacy_base64_decode(encoded)
        assert decoded == original

    def test_roundtrip_edge_cases(self) -> None:
        """边界情况编解码往返。"""
        cases = [b"", b"\x00", b"\xff", b"\x00\xff", b"A" * 100]
        for case in cases:
            encoded = _bytes_to_yacy_base64(case)
            decoded = yacy_base64_decode(encoded)
            # 注意：空字节编码后解码可能有尾随零位差异
            assert decoded[:len(case)] == case

    def test_decode_invalid_char(self) -> None:
        """非法字符应抛出 ValueError。"""
        with pytest.raises(ValueError, match="非法 YaCy Base64 字符"):
            yacy_base64_decode("hello=world")

    def test_target_length_truncation(self) -> None:
        """目标长度截断。"""
        result = _bytes_to_yacy_base64(b"\x12\x34\x56\x78", target_length=3)
        assert len(result) == 3

    def test_target_length_padding(self) -> None:
        """目标长度填充。"""
        result = _bytes_to_yacy_base64(b"\x12", target_length=4)
        assert len(result) == 4
        # 第 2 个字符后应全是 A
        assert result[2:] == "AA"

    def test_decode_roundtrip_bytes(self) -> None:
        """随机字节编解码往返。"""
        import os
        for _ in range(10):
            data = os.urandom(16)
            encoded = _bytes_to_yacy_base64(data)
            decoded = yacy_base64_decode(encoded)
            # 需要处理填充
            min_len = min(len(data), len(decoded))
            assert decoded[:min_len] == data[:min_len]


# ===================================================================
# 词哈希
# ===================================================================


class TestWordHash:
    """词哈希计算测试。"""

    def test_word_to_hash_length(self) -> None:
        """词哈希应为 12 个字符。"""
        h = word_to_hash("hello")
        assert len(h) == WORD_HASH_LENGTH

    def test_word_to_hash_deterministic(self) -> None:
        """相同输入应产生相同哈希。"""
        assert word_to_hash("hello") == word_to_hash("hello")

    def test_word_to_hash_case_insensitive(self) -> None:
        """哈希应对大小写不敏感。"""
        assert word_to_hash("Hello") == word_to_hash("hello")

    def test_word_to_hash_different_words(self) -> None:
        """不同词应产生不同哈希。"""
        assert word_to_hash("hello") != word_to_hash("world")

    def test_word_to_hash_all_valid_chars(self) -> None:
        """哈希中所有字符应在有效字符表中。"""
        for word in ["hello", "world", "python", "YaCy", "搜索"]:
            h = word_to_hash(word)
            for ch in h:
                assert ch in YACY_BASE64_ALPHABET

    def test_words_to_hash_query(self) -> None:
        """多词哈希拼接。"""
        result = words_to_hash_query(["hello", "world"])
        assert len(result) == WORD_HASH_LENGTH * 2
        assert result == word_to_hash("hello") + word_to_hash("world")

    def test_hash_to_words_exclude(self) -> None:
        """排除词哈希。"""
        result = hash_to_words_exclude(["spam", "noise"])
        assert len(result) == WORD_HASH_LENGTH * 2

    def test_word_to_hash_empty_string(self) -> None:
        """空字符串哈希。"""
        h = word_to_hash("")
        assert len(h) == WORD_HASH_LENGTH

    def test_word_to_hash_unicode(self) -> None:
        """Unicode 词的哈希。"""
        h = word_to_hash("中文测试")
        assert len(h) == WORD_HASH_LENGTH
        for ch in h:
            assert ch in YACY_BASE64_ALPHABET


# ===================================================================
# 哈希转换
# ===================================================================


class TestHashConversion:
    """哈希格式转换测试。"""

    def test_b64hash_to_hex_and_back(self) -> None:
        """Base64 → Hex → Base64 往返。"""
        b64 = "sCJ6Tq8T0N9x"
        hex_result = b64hash_to_hex(b64)
        # Hex 长度应该是实际字节数的两倍（Base64 解码后的字节数）
        assert len(hex_result) > 0
        back = hex_to_b64hash(hex_result)
        # 注意可能会有填充差异
        assert back[:len(b64)] == b64

    def test_hex_to_b64hash(self) -> None:
        """Hex → Base64 转换。"""
        hex_str = "deadbeef"
        b64 = hex_to_b64hash(hex_str)
        assert len(b64) >= 5
        for ch in b64:
            assert ch in YACY_BASE64_ALPHABET


# ===================================================================
# 种子字符串
# ===================================================================


class TestSeedString:
    """种子字符串编解码测试。"""

    def test_decode_simple_format(self) -> None:
        """简单格式 p|{...} 的解析。"""
        seed_str = "p|{Hash=sCJ6Tq8T0N9x,Port=8090,PeerType=junior}"
        result = decode_seed_string(seed_str)
        assert result["Hash"] == "sCJ6Tq8T0N9x"
        assert result["Port"] == "8090"
        assert result["PeerType"] == "junior"

    def test_decode_with_escaped_comma(self) -> None:
        """带转义逗号的值。"""
        seed_str = r"p|{Name=hello\, world,PeerType=senior}"
        result = decode_seed_string(seed_str)
        assert result["Name"] == "hello, world"

    def test_decode_with_escaped_backslash(self) -> None:
        """带转义反斜杠的值。"""
        seed_str = r"p|{Path=C:\\data\\index,Type=test}"
        result = decode_seed_string(seed_str)
        assert result["Path"] == "C:\\data\\index"
        assert result["Type"] == "test"

    def test_encode_simple_format(self) -> None:
        """编码为简单格式。"""
        dna = {"Hash": "abc123", "Port": "8090", "PeerType": "junior"}
        encoded = encode_seed_string(dna, compress=False)
        assert encoded.startswith("p|{")
        assert encoded.endswith("}")
        # 解码验证
        decoded = decode_seed_string(encoded)
        assert decoded["Hash"] == "abc123"
        assert decoded["Port"] == "8090"

    def test_encode_compress_format(self) -> None:
        """编码为压缩格式。"""
        dna = {"Hash": "abc123", "Port": "8090", "PeerType": "junior"}
        encoded = encode_seed_string(dna, compress=True)
        assert encoded.startswith("z|")
        # 解码验证
        decoded = decode_seed_string(encoded)
        assert decoded["Hash"] == "abc123"

    def test_decode_compress_format(self) -> None:
        """解码压缩格式。"""
        dna = {"Hash": "testhash12345", "Port": "8090", "Name": "testpeer"}
        compressed = encode_seed_string(dna, compress=True)
        decoded = decode_seed_string(compressed)
        assert decoded["Hash"] == "testhash12345"
        assert decoded["Port"] == "8090"
        assert decoded["Name"] == "testpeer"

    def test_roundtrip_simple(self) -> None:
        """简单格式编解码往返。"""
        original = {
            "Hash": "abcdefghijkl",
            "Port": "8090",
            "PeerType": "senior",
            "Name": "Test Peer",
            "Version": "1.92",
        }
        encoded = encode_seed_string(original, compress=False)
        decoded = decode_seed_string(encoded)
        assert decoded == original

    def test_roundtrip_compressed(self) -> None:
        """压缩格式编解码往返。"""
        original = {
            "Hash": "abcdefghijkl",
            "Port": "8090",
            "PeerType": "senior",
            "Name": "Test Peer with many fields",
            "Version": "1.92",
            "ISpeed": "42",
            "RSpeed": "100",
            "Uptime": "1440",
            "LCount": "1000000",
        }
        encoded = encode_seed_string(original, compress=True)
        decoded = decode_seed_string(encoded)
        assert decoded == original

    def test_decode_empty_string(self) -> None:
        """空字符串应抛出 ValueError。"""
        with pytest.raises(ValueError):
            decode_seed_string("")

    def test_decode_invalid_prefix(self) -> None:
        """非法前缀应抛出 ValueError。"""
        with pytest.raises(ValueError, match="未知种子前缀"):
            decode_seed_string("x|{...}")

    def test_decode_missing_separator(self) -> None:
        """缺少分隔符应抛出 ValueError。"""
        with pytest.raises(ValueError, match="缺少分隔符"):
            decode_seed_string("p{Hash=abc}")


# ===================================================================
# 随机工具
# ===================================================================


class TestRandomTools:
    """随机工具测试。"""

    def test_random_salt(self) -> None:
        """随机盐生成。"""
        salt1 = random_salt()
        salt2 = random_salt()
        assert len(salt1) == 16
        assert salt1 != salt2  # 极小概率相同

    def test_random_salt_custom_length(self) -> None:
        """指定长度的随机盐。"""
        salt = random_salt(8)
        assert len(salt) == 8


# ===================================================================
# 节点哈希
# ===================================================================


class TestPeerHash:
    """节点哈希计算测试。"""

    def test_compute_peer_hash_length(self) -> None:
        """节点哈希应为 12 字符。"""
        h = compute_peer_hash("my-test-peer")
        assert len(h) == WORD_HASH_LENGTH

    def test_compute_peer_hash_deterministic(self) -> None:
        """相同身份产生相同哈希。"""
        assert compute_peer_hash("peer1") == compute_peer_hash("peer1")

    def test_compute_peer_hash_unique(self) -> None:
        """不同身份产生不同哈希。"""
        assert compute_peer_hash("peer1") != compute_peer_hash("peer2")

    def test_compute_peer_hash_valid_chars(self) -> None:
        """哈希中所有字符应在有效字符表中。"""
        h = compute_peer_hash("test-identity-12345")
        for ch in h:
            assert ch in YACY_BASE64_ALPHABET
