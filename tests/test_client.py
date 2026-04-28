# -*- coding: utf-8 -*-
"""PYaCy HTTP 客户端测试套件。

本测试模块覆盖以下方面：
1. 客户端初始化与参数校验
2. 搜索 API 的请求构造与响应解析
3. 状态/版本/网络 API
4. 爬虫控制 API
5. 文档推送 API
6. 错误处理与重试
7. 异常类型正确性

所有测试均使用 unittest.mock 模拟 HTTP 请求，
不需要实际运行 YaCy 实例。
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock
from urllib.error import URLError

import pytest

from pyacy import (
    YaCyClient,
    PYaCyError,
    PYaCyAuthError,
    PYaCyConnectionError,
    PYaCyResponseError,
    PYaCyServerError,
    PYaCyTimeoutError,
    PYaCyValidationError,
)
from pyacy.models import (
    SearchResponse,
    SuggestResponse,
    PeerStatus,
    VersionInfo,
    NetworkInfo,
    PushResponse,
)

from conftest import (
    TEST_BASE_URL,
    make_mock_search_response,
    make_mock_suggest_response,
    make_mock_status_response,
    make_mock_version_response,
    make_mock_network_response,
    make_mock_push_response,
    mock_response,
)


# ======================================================================
# 1. 客户端初始化测试
# ======================================================================


class TestClientInit:
    """测试 YaCyClient 初始化。"""

    def test_default_init(self):
        """默认参数初始化。"""
        client = YaCyClient()
        assert client.base_url == "http://localhost:8090"
        assert client.timeout == 30.0
        assert client.auth is None

    def test_custom_url(self):
        """自定义 base_url。"""
        client = YaCyClient("https://my-yacy:8443")
        assert client.base_url == "https://my-yacy:8443"

    def test_url_trailing_slash_stripped(self):
        """URL 末尾斜杠应被移除。"""
        client = YaCyClient("http://localhost:8090/")
        assert client.base_url == "http://localhost:8090"

    def test_invalid_url_raises(self):
        """无效 URL 应抛出 PYaCyValidationError。"""
        with pytest.raises(PYaCyValidationError, match="必须以 http:// 或 https:// 开头"):
            YaCyClient("localhost:8090")

    def test_with_auth(self):
        """带认证的初始化。"""
        client = YaCyClient(auth=("admin", "password123"))
        assert client.auth == ("admin", "password123")

    def test_verify_ssl_disabled(self):
        """禁用 SSL 验证。"""
        client = YaCyClient(verify_ssl=False)
        assert client.verify_ssl is False

    def test_user_agent_header(self):
        """检查 User-Agent 请求头。"""
        client = YaCyClient()
        assert "PYaCy" in client._default_headers["User-Agent"]


# ======================================================================
# 2. 内部工具方法测试
# ======================================================================


class TestInternalMethods:
    """测试内部工具方法。"""

    def test_build_url(self, client):
        """URL 构建。"""
        assert client._build_url("/yacysearch.json") == "http://localhost:8090/yacysearch.json"
        assert client._build_url("yacysearch.json") == "http://localhost:8090/yacysearch.json"
        assert client._build_url("/api/version.json") == "http://localhost:8090/api/version.json"

    def test_clean_params_removes_none(self, client):
        """clean_params 应移除 None 值。"""
        params = {"a": 1, "b": None, "c": "hello"}
        cleaned = client._clean_params(params)
        assert cleaned == {"a": 1, "c": "hello"}

    def test_clean_params_none_input(self, client):
        """clean_params 输入 None 返回 None。"""
        assert client._clean_params(None) is None

    def test_clean_params_empty_input(self, client):
        """clean_params 输入空字典返回空字典。"""
        assert client._clean_params({}) == {}

    def test_context_manager(self):
        """测试上下文管理器。"""
        with YaCyClient() as client:
            assert client.base_url == "http://localhost:8090"

    def test_repr(self, client):
        """测试 repr 输出。"""
        r = repr(client)
        assert "YaCyClient" in r
        assert TEST_BASE_URL in r


# ======================================================================
# 3. 搜索 API 测试
# ======================================================================


class TestSearchAPI:
    """测试搜索相关 API。"""

    def test_search_basic(self, client):
        """基本搜索请求。"""
        mock_data = make_mock_search_response(query="python")
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            result = client.search("python")

            assert isinstance(result, SearchResponse)
            assert result.query == "python"
            assert result.total_results == 42
            assert len(result.items) == 2
            assert result.items[0].title == "Test Result 1"
            assert result.items[0].link == "http://example.com/1"

    def test_search_empty_query_raises(self, client):
        """空关键词应抛出异常。"""
        with pytest.raises(PYaCyValidationError, match="不能为空"):
            client.search("")

    def test_search_whitespace_query_raises(self, client):
        """纯空白关键词应抛出异常。"""
        with pytest.raises(PYaCyValidationError, match="不能为空"):
            client.search("   ")

    def test_search_with_all_params(self, client):
        """带所有搜索参数的请求。"""
        mock_data = make_mock_search_response(query="python", total_results=0)
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            result = client.search(
                "python",
                resource="global",
                maximum_records=20,
                start_record=10,
                content_dom="text",
                verify="true",
                url_mask_filter=r".*\.pdf$",
                prefer_mask_filter="wikipedia",
                language="lang_en",
                navigators="all",
            )

            call_kwargs = mock_req.call_args.kwargs
            params = call_kwargs["params"]
            assert params["query"] == "python"
            assert params["resource"] == "global"
            assert params["maximumRecords"] == 20
            assert params["startRecord"] == 10
            assert params["contentdom"] == "text"
            assert params["verify"] == "true"
            assert params["urlmaskfilter"] == r".*\.pdf$"
            assert params["prefermaskfilter"] == "wikipedia"
            assert params["lr"] == "lang_en"
            assert params["nav"] == "all"

            assert isinstance(result, SearchResponse)

    def test_search_pagination(self, client):
        """分页信息正确性。"""
        mock_data = make_mock_search_response(total_results=100)
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            result = client.search("test", maximum_records=10)

            assert result.total_pages == 10

    def test_search_zero_items_per_page(self, client):
        """itemsPerPage 为 0 时 total_pages 应返回 0。"""
        data = make_mock_search_response()
        data["channels"][0]["itemsPerPage"] = 0
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=data)
            result = client.search("test")
            assert result.total_pages == 0

    def test_search_empty_channels(self, client):
        """空 channels 响应。"""
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data={"channels": []})
            result = client.search("test")
            assert result.items == []
            assert result.total_results == 0

    def test_suggest_basic(self, client):
        """基本搜索建议。"""
        mock_data = make_mock_suggest_response()
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            result = client.suggest("pyth")

            assert isinstance(result, SuggestResponse)
            assert len(result.suggestions) == 3
            assert result.suggestions[0].word == "python"

    def test_suggest_empty_query_raises(self, client):
        """空建议查询应抛出异常。"""
        with pytest.raises(PYaCyValidationError, match="不能为空"):
            client.suggest("")

    def test_suggest_single_item(self, client):
        """单条建议响应。"""
        mock_data = [{"suggestion": "python"}]
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            result = client.suggest("py")
            assert len(result.suggestions) == 1


# ======================================================================
# 4. 状态/版本/网络 API 测试
# ======================================================================


class TestStatusAPI:
    """测试状态相关 API。"""

    def test_status(self, client):
        """节点状态查询。"""
        mock_data = make_mock_status_response()
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            status = client.status()

            assert isinstance(status, PeerStatus)
            assert status.status == "running"
            assert status.uptime == 3600000
            assert status.index_size == 12345

    def test_status_memory_properties(self, client):
        """状态对象的内存计算属性。"""
        mock_data = make_mock_status_response()
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            status = client.status()

            expected_used = (1073741824 - 536870912) / (1024 * 1024)
            assert status.memory_used_mb == pytest.approx(expected_used, rel=0.01)
            assert status.uptime_hours == 1.0

    def test_version(self, client):
        """版本信息查询。"""
        mock_data = make_mock_version_response()
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            vi = client.version()

            assert isinstance(vi, VersionInfo)
            assert vi.version == "1.93"
            assert vi.svn_revision == "12345"
            assert vi.java_version == "17.0.8"

    def test_network(self, client):
        """网络统计信息查询。"""
        mock_data = make_mock_network_response()
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            net = client.network()

            assert isinstance(net, NetworkInfo)
            assert net.active_peers == 150
            assert net.passive_peers == 50
            assert net.total_urls == 123456789
            assert net.peer_name == "test-peer"
            assert net.peer_hash == "abc123hash"


# ======================================================================
# 5. 爬虫控制 API 测试
# ======================================================================


class TestCrawlerAPI:
    """测试爬虫控制相关 API。"""

    def test_crawl_start_basic(self, client):
        """基本爬虫启动。"""
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(text="OK")
            result = client.crawl_start("https://example.com")

            assert result["status_code"] == 200
            assert result["start_url"] == "https://example.com"

    def test_crawl_start_empty_url_raises(self, client):
        """空 URL 应抛出异常。"""
        with pytest.raises(PYaCyValidationError, match="不能为空"):
            client.crawl_start("")

    def test_crawl_start_with_all_params(self, client):
        """带所有爬虫参数的请求。"""
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(text="OK")
            result = client.crawl_start(
                "https://example.com",
                crawling_depth=3,
                must_match=r"example\.com/.*",
                must_not_match=r"example\.com/admin.*",
                index_text=True,
                index_media=False,
            )

            call_kwargs = mock_req.call_args.kwargs
            assert call_kwargs["data"]["crawlingDepth"] == "3"
            assert call_kwargs["data"]["mustmatch"] == r"example\.com/.*"
            assert call_kwargs["data"]["mustnotmatch"] == r"example\.com/admin.*"

    def test_crawl_start_expert(self, client):
        """专家模式爬虫启动。"""
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(text="OK")
            result = client.crawl_start_expert(
                "https://example.com",
                crawl_order="fill",
            )
            assert result["status_code"] == 200

    def test_crawl_start_expert_empty_url(self, client):
        """专家模式空 URL。"""
        with pytest.raises(PYaCyValidationError, match="不能为空"):
            client.crawl_start_expert("")


# ======================================================================
# 6. 文档推送 API 测试
# ======================================================================


class TestPushAPI:
    """测试文档推送相关 API。"""

    def test_push_document(self, client):
        """基本文档推送。"""
        mock_data = make_mock_push_response(success=True)
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            result = client.push_document(
                url="http://example.com/doc.html",
                content="<html><body>Test</body></html>",
                content_type="text/html",
            )

            assert isinstance(result, PushResponse)
            assert result.success_all is True
            assert result.success_count == 1
            assert result.fail_count == 0

    def test_push_document_failed(self, client):
        """推送失败的响应处理。"""
        mock_data = make_mock_push_response(success=False)
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            result = client.push_document(
                url="http://example.com/bad.html",
                content="corrupted data",
            )

            assert result.success_all is False
            assert result.success_count == 0
            assert result.fail_count == 1

    def test_push_document_with_all_metadata(self, client):
        """带所有元数据的文档推送。"""
        mock_data = make_mock_push_response(success=True)
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            result = client.push_document(
                url="http://example.com/image.png",
                content=b"\x89PNG fake",
                content_type="image/png",
                collection="test_images",
                last_modified="Tue, 15 Nov 2024 12:45:26 GMT",
                title="Test Image",
                keywords="test sample",
            )

            assert result.success_all is True
            # 新版本 responseHeader-0 使用逗号拼接
            call_kwargs = mock_req.call_args.kwargs
            headers = call_kwargs["data"]["responseHeader-0"]
            assert "X-YaCy-Media-Title:Test Image" in headers
            assert "X-YaCy-Media-Keywords:test sample" in headers

    def test_push_document_empty_url_raises(self, client):
        """空 URL 应抛出异常。"""
        with pytest.raises(PYaCyValidationError, match="不能为空"):
            client.push_document(url="", content="test")

    def test_push_documents_batch(self, client):
        """批量推送文档。"""
        mock_data = {
            "count": "2",
            "successall": "true",
            "item-0": {"item": "0", "url": "http://ex.com/1", "success": "true", "message": "ok"},
            "item-1": {"item": "1", "url": "http://ex.com/2", "success": "true", "message": "ok"},
            "countsuccess": 2,
            "countfail": 0,
        }
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            result = client.push_documents_batch([
                {"url": "http://ex.com/1", "content": "doc1"},
                {"url": "http://ex.com/2", "content": "doc2"},
            ])

            assert result.total_count == 2
            assert result.success_count == 2
            assert len(result.items) == 2

    def test_push_documents_batch_empty_raises(self, client):
        """空批量推送。"""
        with pytest.raises(PYaCyValidationError, match="不能为空"):
            client.push_documents_batch([])

    def test_push_documents_batch_missing_url_raises(self, client):
        """批量推送中缺少 URL。"""
        with pytest.raises(PYaCyValidationError, match="缺少 url"):
            client.push_documents_batch([{"content": "test"}])


# ======================================================================
# 7. 索引管理与黑名单 API 测试
# ======================================================================


class TestIndexManagement:
    """测试索引管理和黑名单 API。"""

    def test_delete_index_by_url(self, client):
        """按 URL 删除索引。"""
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(text="OK")
            result = client.delete_index(url="http://example.com/remove.html")
            assert result["status_code"] == 200

    def test_delete_index_by_host(self, client):
        """按主机删除索引。"""
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(text="OK")
            result = client.delete_index(host="example.com")
            assert result["status_code"] == 200

    def test_delete_index_all(self, client):
        """全量删除索引。"""
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(text="OK")
            result = client.delete_index(delete_all=True)
            assert result["status_code"] == 200

    def test_delete_index_no_target_raises(self, client):
        """无删除目标应抛出异常。"""
        with pytest.raises(PYaCyValidationError, match="必须指定至少一个"):
            client.delete_index()

    def test_get_blacklists(self, client):
        """获取黑名单元数据。"""
        mock_data = {"lists": []}
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            result = client.get_blacklists()
            assert result == {"lists": []}

    def test_get_blacklist(self, client):
        """获取指定黑名单。"""
        mock_data = {"entries": [{"pattern": "spam.com"}]}
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            result = client.get_blacklist("my_list")
            assert "entries" in result

    def test_get_blacklist_empty_name_raises(self, client):
        """空黑名单名称。"""
        with pytest.raises(PYaCyValidationError, match="不能为空"):
            client.get_blacklist("")

    def test_add_blacklist_entry(self, client):
        """添加黑名单条目。"""
        mock_data = {"status": "ok"}
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            result = client.add_blacklist_entry("my_list", "spam.com")
            assert result == {"status": "ok"}


# ======================================================================
# 8. 错误处理与重试测试
# ======================================================================


class TestErrorHandling:
    """测试错误处理行为。

    _request 的内部实现了状态码检查和异常转换。
    本类测试验证这些异常能正确传递给上层 API。
    """

    def test_connection_error(self, client):
        """网络连接失败 — _request 抛出 PYaCyConnectionError。"""
        with patch.object(client, "_request") as mock_req:
            mock_req.side_effect = PYaCyConnectionError(
                "无法连接到 YaCy 服务",
                original_error=URLError("拒绝连接"),
            )
            with pytest.raises(PYaCyConnectionError, match="无法连接到 YaCy"):
                client.search("test")

    def test_timeout_error(self, client):
        """请求超时 — _request 抛出 PYaCyTimeoutError。"""
        with patch.object(client, "_request") as mock_req:
            mock_req.side_effect = PYaCyTimeoutError(
                "请求超时", timeout=30.0
            )
            with pytest.raises(PYaCyTimeoutError, match="请求超时"):
                client.search("test")

    def test_auth_error_401(self, client):
        """认证失败 401 — _request 抛出 PYaCyAuthError。"""
        with patch.object(client, "_request") as mock_req:
            mock_req.side_effect = PYaCyAuthError(
                "认证失败: 需要提供有效的用户名和密码",
                status_code=401,
            )
            with pytest.raises(PYaCyAuthError, match="认证失败"):
                client.search("test")

    def test_auth_error_403(self, client):
        """认证失败 403 — _request 抛出 PYaCyAuthError。"""
        with patch.object(client, "_request") as mock_req:
            mock_req.side_effect = PYaCyAuthError(
                "访问被拒绝: 当前凭据无权访问此 API",
                status_code=403,
            )
            with pytest.raises(PYaCyAuthError, match="访问被拒绝"):
                client.search("test")

    def test_server_error_500(self, client):
        """服务端错误 500 — _request 抛出 PYaCyServerError。"""
        with patch.object(client, "_request") as mock_req:
            mock_req.side_effect = PYaCyServerError(
                "YaCy 服务端错误 (HTTP 500)",
                status_code=500,
                response_body="Internal Error",
            )
            with pytest.raises(PYaCyServerError, match="服务端错误"):
                client.search("test")

    def test_server_error_503(self, client):
        """服务端错误 503 — _request 抛出 PYaCyServerError。"""
        with patch.object(client, "_request") as mock_req:
            mock_req.side_effect = PYaCyServerError(
                "YaCy 服务端错误 (HTTP 503)",
                status_code=503,
            )
            with pytest.raises(PYaCyServerError):
                client.search("test")

    def test_client_error_400(self, client):
        """客户端错误 400 — _request 抛出 PYaCyResponseError。"""
        with patch.object(client, "_request") as mock_req:
            mock_req.side_effect = PYaCyResponseError(
                "API 返回错误 (HTTP 400)",
                status_code=400,
            )
            with pytest.raises(PYaCyResponseError):
                client.search("test")

    def test_invalid_json_response(self, client):
        """无效 JSON 响应由 _get_json 抛出 PYaCyResponseError。"""
        with patch.object(client, "_request") as mock_req:
            # 返回 200 但文本不是 JSON — _get_json 会解析失败
            mock_req.return_value = mock_response(
                status_code=200, text="<html>Not JSON</html>"
            )
            with pytest.raises(PYaCyResponseError, match="无法解析 JSON"):
                client.search("test")

    def test_exception_hierarchy(self):
        """验证异常层次结构。"""
        assert issubclass(PYaCyAuthError, PYaCyResponseError)
        assert issubclass(PYaCyResponseError, PYaCyError)
        assert issubclass(PYaCyServerError, PYaCyResponseError)
        assert issubclass(PYaCyConnectionError, PYaCyError)
        assert issubclass(PYaCyTimeoutError, PYaCyError)
        assert issubclass(PYaCyValidationError, PYaCyError)

    def test_connection_error_stores_original(self):
        """连接异常应保存原始异常。"""
        original = URLError("no route to host")
        exc = PYaCyConnectionError("连接失败", original_error=original)
        assert exc.original_error is original

    def test_timeout_error_stores_timeout_value(self):
        """超时异常应保存超时值。"""
        exc = PYaCyTimeoutError("超时了", timeout=15.0)
        assert exc.timeout == 15.0

    def test_response_error_stores_details(self):
        """响应异常应保存状态码和响应体。"""
        exc = PYaCyResponseError("错误", status_code=404, response_body="Not Found")
        assert exc.status_code == 404
        assert exc.response_body == "Not Found"


# ======================================================================
# 9. Ping 测试
# ======================================================================


class TestPing:
    """测试 ping 功能。"""

    def test_ping_success(self, client):
        """ping 成功。"""
        mock_data = make_mock_version_response()
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            assert client.ping() is True

    def test_ping_failure(self, client):
        """ping 失败（连接错误）。"""
        with patch.object(client, "_request") as mock_req:
            mock_req.side_effect = PYaCyConnectionError(
                "无法连接", original_error=URLError("拒接")
            )
            assert client.ping() is False


# ======================================================================
# 10. 数据模型测试
# ======================================================================


class TestDataModels:
    """测试数据模型的构造和转换。"""

    def test_search_result_from_json(self):
        """从字典构造 SearchResult。"""
        from pyacy.models import SearchResult

        data = {
            "title": "Python 官网",
            "link": "https://python.org",
            "description": "Python <b>编程</b>语言",
            "pubDate": "2024-01-01",
            "sizename": "1024 kbyte",
            "host": "python.org",
            "path": "/",
            "file": "/",
            "guid": "py_guid_001",
        }
        result = SearchResult.from_json_item(data)
        assert result.title == "Python 官网"
        assert result.link == "https://python.org"
        assert result.host == "python.org"

    def test_suggest_response_from_json(self):
        """从列表构造 SuggestResponse。"""
        data = [{"suggestion": "python"}, {"suggestion": "python3"}]
        resp = SuggestResponse.from_json(data)
        assert len(resp.suggestions) == 2
        assert resp.suggestions[0].word == "python"

    def test_suggest_response_empty(self):
        """空建议列表。"""
        resp = SuggestResponse.from_json([])
        assert resp.suggestions == []

    def test_peer_status_from_json(self):
        """从字典构造 PeerStatus。"""
        data = {
            "status": "online",
            "uptime": 7200000,
            "totalMemory": 2147483648,
            "freeMemory": 1073741824,
            "indexSize": 50000,
        }
        ps = PeerStatus.from_json(data)
        assert ps.status == "online"
        assert ps.uptime_hours == 2.0
        assert ps.memory_used_mb == pytest.approx(1024.0, rel=0.01)

    def test_version_info_from_json(self):
        """从字典构造 VersionInfo。"""
        data = {"version": "1.94", "svnRevision": "12346", "buildDate": "2025-01-01"}
        vi = VersionInfo.from_json(data)
        assert vi.version == "1.94"

    def test_network_info_from_json(self):
        """从字典构造 NetworkInfo。"""
        data = {
            "peers": {
                "your": {"name": "my-node", "hash": "hash123"},
                "all": {"active": 200, "passive": 30, "potential": 100, "count": 999999},
            }
        }
        ni = NetworkInfo.from_json(data)
        assert ni.peer_name == "my-node"
        assert ni.active_peers == 200
        assert ni.total_urls == 999999

    def test_push_response_from_json(self):
        """从字典构造 PushResponse。"""
        data = make_mock_push_response(success=True)
        pr = PushResponse.from_json(data)
        assert pr.success_all is True
        assert pr.total_count == 1
        assert pr.success_count == 1
        assert pr.fail_count == 0
        assert len(pr.items) == 1


# ======================================================================
# 11. 边界情况测试
# ======================================================================


class TestEdgeCases:
    """测试边界情况。"""

    def test_search_no_title(self, client):
        """搜索结果无标题。"""
        item = {"link": "http://x.com/1", "description": "...", "host": "x.com"}
        mock_data = make_mock_search_response(items=[item])
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            result = client.search("test")
            assert result.items[0].title == ""

    def test_search_no_link(self, client):
        """搜索结果无链接。"""
        item = {"title": "X", "description": "...", "host": "x.com"}
        mock_data = make_mock_search_response(items=[item])
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            result = client.search("test")
            assert result.items[0].link == ""

    def test_url_with_special_chars_in_params(self, client):
        """URL 中的特殊字符应正确编码。"""
        mock_data = make_mock_search_response()
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(json_data=mock_data)
            client.search("c++ & rust")
            call_args = mock_req.call_args
            params = call_args.kwargs["params"]
            assert params["query"] == "c++ & rust"

    def test_version_missing_fields(self, client):
        """版本信息缺少可选字段。"""
        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = mock_response(
                json_data={"version": "1.0"}
            )
            vi = client.version()
            assert vi.version == "1.0"
