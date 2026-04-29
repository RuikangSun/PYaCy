# -*- coding: utf-8 -*-
"""YaCy SimpleCoding 解码与资源解析单元测试。

测试 ``pyacy.utils`` 和 ``pyacy.dht.search`` 中新增的函数（v0.3.1）：
- ``simplecoding_decode()`` SimpleCoding 值解码
- ``simplecoding_decode_bytes()`` SimpleCoding 值解码为字节
- ``parse_search_resource()`` 搜索结果资源解析
- ``_parse_resources()`` 多资源解析
- ``_parse_index_counts()`` 索引计数解析
- ``_parse_index_abstracts()`` 索引摘要解析
"""

import os
import sys
import base64

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pyacy.utils import (
    simplecoding_decode,
    simplecoding_decode_bytes,
    parse_search_resource,
)
from pyacy.dht.search import (
    _parse_resources,
    _parse_index_counts,
    _parse_index_abstracts,
    _parse_search_response,
    DHTReference,
    DHTSearchResult,
)
from pyacy.p2p.protocol import P2PResponse


# ---------------------------------------------------------------------------
# 1. SimpleCoding 解码测试
# ---------------------------------------------------------------------------


class TestSimpleCodingDecode:
    """测试 simplecoding_decode() 函数。"""

    def test_base64_encoded(self):
        """b| 前缀应解码 Base64 数据。"""
        encoded = base64.b64encode(b"hello world").decode("ascii")
        result = simplecoding_decode(f"b|{encoded}")
        assert result == "hello world"

    def test_plain_text(self):
        """p| 前缀应返回明文。"""
        result = simplecoding_decode("p|world")
        assert result == "world"

    def test_no_prefix(self):
        """无管道符时返回原值。"""
        result = simplecoding_decode("hello")
        assert result == "hello"

    def test_empty_string(self):
        """空字符串返回空。"""
        assert simplecoding_decode("") == ""

    def test_invalid_base64(self):
        """无效 Base64 应返回原始数据。"""
        result = simplecoding_decode("b|invalid!!!")
        assert result == "invalid!!!"

    def test_url_encoding(self):
        """URL 的 Base64 编码应正确解码。"""
        url = "https://www.shanghaitech.edu.cn/research/"
        encoded = base64.b64encode(url.encode("utf-8")).decode("ascii")
        result = simplecoding_decode(f"b|{encoded}")
        assert result == url

    def test_chinese_content(self):
        """中文内容的 Base64 应正确解码。"""
        text = "上海科技大学 - 立志 成才 报国 裕民"
        encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
        result = simplecoding_decode(f"b|{encoded}")
        assert result == text

    def test_multiline_content(self):
        """多行内容应正确处理。"""
        text = "Line 1\nLine 2\nLine 3"
        encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
        result = simplecoding_decode(f"b|{encoded}")
        assert result == text

    def test_html_content(self):
        """HTML 内容应正确处理。"""
        html = "<p>测试内容 &amp; 更多</p>"
        encoded = base64.b64encode(html.encode("utf-8")).decode("ascii")
        result = simplecoding_decode(f"b|{encoded}")
        assert result == html

    def test_uuid_content(self):
        """UUID 格式应正确处理。"""
        uuid = "550e8400-e29b-41d4-a716-446655440000"
        encoded = base64.b64encode(uuid.encode("utf-8")).decode("ascii")
        result = simplecoding_decode(f"b|{encoded}")
        assert result == uuid


class TestSimpleCodingDecodeBytes:
    """测试 simplecoding_decode_bytes() 函数。"""

    def test_base64_to_bytes(self):
        """b| 前缀应解码为字节。"""
        encoded = base64.b64encode(b"binary data").decode("ascii")
        result = simplecoding_decode_bytes(f"b|{encoded}")
        assert result == b"binary data"

    def test_plain_to_bytes(self):
        """p| 前缀应编码为字节。"""
        result = simplecoding_decode_bytes("p|text")
        assert result == b"text"

    def test_no_prefix_to_bytes(self):
        """无管道符时编码为字节。"""
        result = simplecoding_decode_bytes("hello")
        assert result == b"hello"

    def test_empty_to_bytes(self):
        """空字符串返回空字节。"""
        assert simplecoding_decode_bytes("") == b""


# ---------------------------------------------------------------------------
# 2. 搜索资源解析测试
# ---------------------------------------------------------------------------


class TestParseSearchResource:
    """测试 parse_search_resource() 函数。"""

    def test_basic_resource(self):
        """基本资源解析。"""
        resource_str = "{hash=abc123,url=p|http://example.com,descr=p|Test page}"
        result = parse_search_resource(resource_str)
        assert result["hash"] == "abc123"
        assert result["url"] == "http://example.com"
        assert result["descr"] == "Test page"

    def test_base64_values(self):
        """Base64 编码的值应解码。"""
        url = "https://www.example.com/page"
        url_b64 = base64.b64encode(url.encode("utf-8")).decode("ascii")
        resource_str = f"{{hash=xyz789,url=b|{url_b64}}}"
        result = parse_search_resource(resource_str)
        assert result["url"] == url

    def test_multiple_fields(self):
        """多个字段应正确解析。"""
        resource_str = "{hash=abc,url=p|http://a.com,title=p|Page Title,descr=p|Description,size=12345,wordcount=500}"
        result = parse_search_resource(resource_str)
        assert result["hash"] == "abc"
        assert result["url"] == "http://a.com"
        assert result["title"] == "Page Title"
        assert result["descr"] == "Description"
        assert result["size"] == "12345"
        assert result["wordcount"] == "500"

    def test_empty_string(self):
        """空字符串返回空字典。"""
        result = parse_search_resource("")
        assert result == {}

    def test_empty_braces(self):
        """空花括号返回空字典。"""
        result = parse_search_resource("{}")
        assert result == {}

    def test_no_braces(self):
        """无花括号时也能解析。"""
        resource_str = "hash=abc,url=p|http://example.com"
        result = parse_search_resource(resource_str)
        assert result["hash"] == "abc"
        assert result["url"] == "http://example.com"

    def test_real_yacy_resource(self):
        """解析真实的 YaCy resource 格式。"""
        # 模拟真实 YaCy 响应
        url = "https://www.shanghaitech.edu.cn/page/5/"
        url_b64 = base64.b64encode(url.encode("utf-8")).decode("ascii")
        title = "上海科技大学 (第5页)"
        title_b64 = base64.b64encode(title.encode("utf-8")).decode("ascii")
        descr = "生化环材 科普 知识 游戏"
        descr_b64 = base64.b64encode(descr.encode("utf-8")).decode("ascii")

        resource_str = f"{{hash=_2L_FlPN-Az4,url=b|{url_b64},title=b|{title_b64},descr=b|{descr_b64},size=12345,wordcount=100,lastModified=1700000000000,en}}"

        result = parse_search_resource(resource_str)
        assert result["hash"] == "_2L_FlPN-Az4"
        assert result["url"] == url
        assert result["title"] == title
        assert result["descr"] == descr


# ---------------------------------------------------------------------------
# 3. 多资源解析测试
# ---------------------------------------------------------------------------


class TestParseResources:
    """测试 _parse_resources() 函数。"""

    def test_single_resource(self):
        """单个 resource 应正确解析。"""
        url = "http://example.com"
        url_b64 = base64.b64encode(url.encode("utf-8")).decode("ascii")
        data = {
            "resource0": f"{{hash=abc123,url=b|{url_b64},title=p|Test Page}}",
        }
        refs, links = _parse_resources(data)
        assert len(refs) == 1
        assert refs[0].url_hash == "abc123"
        assert refs[0].url == url
        assert refs[0].title == "Test Page"
        assert links == [url]

    def test_multiple_resources(self):
        """多个 resource 应去重合并。"""
        url1 = "http://a.com"
        url2 = "http://b.com"
        url1_b64 = base64.b64encode(url1.encode("utf-8")).decode("ascii")
        url2_b64 = base64.b64encode(url2.encode("utf-8")).decode("ascii")

        data = {
            "resource0": f"{{hash=aaa,url=b|{url1_b64}}}",
            "resource1": f"{{hash=bbb,url=b|{url2_b64}}}",
        }
        refs, links = _parse_resources(data)
        assert len(refs) == 2
        assert len(links) == 2
        assert set(links) == {url1, url2}

    def test_duplicate_urls_dedup(self):
        """重复 URL 应去重。"""
        url = "http://same.com"
        url_b64 = base64.b64encode(url.encode("utf-8")).decode("ascii")

        data = {
            "resource0": f"{{hash=aaa,url=b|{url_b64}}}",
            "resource1": f"{{hash=bbb,url=b|{url_b64}}}",
        }
        refs, links = _parse_resources(data)
        assert len(refs) == 2  # 两个引用
        assert len(links) == 1  # 但只有一个去重链接

    def test_no_resources(self):
        """无 resource 字段时返回空。"""
        data = {"searchtime": "100", "joincount": "5"}
        refs, links = _parse_resources(data)
        assert refs == []
        assert links == []

    def test_missing_fields_defaults(self):
        """缺失字段应使用默认值。"""
        data = {
            "resource0": "{hash=abc}",
        }
        refs, links = _parse_resources(data)
        assert len(refs) == 1
        assert refs[0].url_hash == "abc"
        assert refs[0].url == ""
        assert refs[0].title == ""
        assert refs[0].size == 0

    def test_realistic_response(self):
        """解析模拟的真实 YaCy 响应。"""
        url1 = "https://www.shanghaitech.edu.cn/research/"
        url2 = "https://www.shanghaitech.edu.cn/"
        url1_b64 = base64.b64encode(url1.encode("utf-8")).decode("ascii")
        url2_b64 = base64.b64encode(url2.encode("utf-8")).decode("ascii")

        data = {
            "version": "1.940",
            "uptime": "76",
            "searchtime": "95",
            "references": "科研,shanghaitech,research",
            "joincount": "5871",
            "count": "2",
            "resource0": f"{{hash=abc123,url=b|{url1_b64},title=p|Tag: 化学}}",
            "resource1": f"{{hash=def456,url=b|{url2_b64},title=p|上海科技大学官网}}",
        }
        refs, links = _parse_resources(data)
        assert len(refs) == 2
        assert refs[0].url == url1
        assert refs[0].title == "Tag: 化学"
        assert refs[1].url == url2
        assert refs[1].title == "上海科技大学官网"
        assert set(links) == {url1, url2}


# ---------------------------------------------------------------------------
# 4. 索引计数和摘要解析测试
# ---------------------------------------------------------------------------


class TestParseIndexCounts:
    """测试 _parse_index_counts() 函数。"""

    def test_basic_parsing(self):
        """基本索引计数解析。"""
        data = {
            "indexcount.abc123": "100",
            "indexcount.def456": "50",
            "other_field": "ignore",
        }
        result = _parse_index_counts(data)
        assert result == {"abc123": 100, "def456": 50}

    def test_empty(self):
        """空数据返回空字典。"""
        assert _parse_index_counts({}) == {}

    def test_invalid_value(self):
        """无效值应返回 0。"""
        data = {"indexcount.abc": "invalid"}
        result = _parse_index_counts(data)
        assert result == {"abc": 0}


class TestParseIndexAbstracts:
    """测试 _parse_index_abstracts() 函数。"""

    def test_basic_parsing(self):
        """基本索引摘要解析。"""
        data = {
            "indexabstract.abc123": "摘要内容",
            "indexabstract.def456": "更多内容",
            "other_field": "ignore",
        }
        result = _parse_index_abstracts(data)
        assert result == {"abc123": "摘要内容", "def456": "更多内容"}

    def test_empty(self):
        """空数据返回空字典。"""
        assert _parse_index_abstracts({}) == {}


# ---------------------------------------------------------------------------
# 5. 完整搜索响应解析测试
# ---------------------------------------------------------------------------


class TestParseSearchResponseFull:
    """测试 _parse_search_response() 完整流程。"""

    def test_realistic_yacy_response(self):
        """解析模拟的真实 YaCy DHT 搜索响应。"""
        url = "https://www.shanghaitech.edu.cn/research/"
        url_b64 = base64.b64encode(url.encode("utf-8")).decode("ascii")
        title = "Tag: 科研 | 上海科技大学官网"
        title_b64 = base64.b64encode(title.encode("utf-8")).decode("ascii")
        descr = "科研教育机构网站"
        descr_b64 = base64.b64encode(descr.encode("utf-8")).decode("ascii")

        raw_text = (
            "version=1.940\n"
            "uptime=76\n"
            "searchtime=95\n"
            "references=科研,shanghaitech,research,science\n"
            "joincount=5871\n"
            "count=1\n"
            f"resource0={{hash=_2L_FlPN-Az4,url=b|{url_b64},title=b|{title_b64},descr=b|{descr_b64},size=12345,wordcount=100}}\n"
            "indexcount.abc123=100\n"
            "indexabstract.abc123=摘要文本\n"
        )

        response = P2PResponse(raw_text)
        result = _parse_search_response(response)

        assert result.success is True
        assert result.search_time_ms == 95
        assert result.join_count == 5871
        assert result.link_count == 1
        assert len(result.references) == 1
        assert result.references[0].url == url
        assert result.references[0].title == title
        assert result.references[0].description == descr
        assert result.references[0].url_hash == "_2L_FlPN-Az4"
        assert result.references[0].size == 12345
        assert result.references[0].word_count == 100
        assert len(result.links) == 1
        assert result.links[0] == url

    def test_empty_response(self):
        """空响应应返回空结果。"""
        raw_text = ""
        response = P2PResponse(raw_text)
        result = _parse_search_response(response)
        assert result.success is True
        assert result.references == []
        assert result.links == []

    def test_searchtime_parsing(self):
        """searchtime 字段应正确解析。"""
        raw_text = "searchtime=123\n"
        response = P2PResponse(raw_text)
        result = _parse_search_response(response)
        assert result.search_time_ms == 123

    def test_invalid_searchtime(self):
        """无效 searchtime 应返回 0。"""
        raw_text = "searchtime=abc\n"
        response = P2PResponse(raw_text)
        result = _parse_search_response(response)
        assert result.search_time_ms == 0

    def test_multiple_resources_with_chinese(self):
        """多个包含中文的 resource 应正确解析。"""
        url1 = "https://www.shanghaitech.edu.cn/research/"
        url2 = "https://www.shanghaitech.edu.cn/"
        url1_b64 = base64.b64encode(url1.encode("utf-8")).decode("ascii")
        url2_b64 = base64.b64encode(url2.encode("utf-8")).decode("ascii")

        raw_text = (
            "searchtime=200\n"
            "joincount=1000\n"
            "count=2\n"
            f"resource0={{hash=aaa,url=b|{url1_b64},title=p|科研标签页}}\n"
            f"resource1={{hash=bbb,url=b|{url2_b64},title=p|上海科技大学官网主页}}\n"
        )

        response = P2PResponse(raw_text)
        result = _parse_search_response(response)

        assert len(result.references) == 2
        assert len(result.links) == 2
        assert set(result.links) == {url1, url2}
        titles = [r.title for r in result.references]
        assert "科研标签页" in titles
        assert "上海科技大学官网主页" in titles
