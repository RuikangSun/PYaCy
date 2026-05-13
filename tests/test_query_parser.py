# -*- coding: utf-8 -*-
"""SearchQuery 解析器单元测试。

覆盖所有 YaCy 高级搜索语法操作符的解析和客户端侧过滤功能。
"""

import unittest
from unittest.mock import MagicMock

from pyacy.search.query_parser import SearchQuery


class TestSearchQueryParsing(unittest.TestCase):
    """测试 SearchQuery.parse() 解析各种操作符。"""

    def test_empty_query(self):
        q = SearchQuery.parse("")
        self.assertEqual(q.clean_query, "")
        self.assertFalse(q.has_filters)

    def test_plain_query_no_operators(self):
        q = SearchQuery.parse("python tutorial")
        self.assertEqual(q.clean_query, "python tutorial")
        self.assertFalse(q.has_filters)

    def test_site_operator(self):
        q = SearchQuery.parse("site:example.com python")
        self.assertEqual(q.site, "example.com")
        self.assertEqual(q.clean_query, "python")
        self.assertTrue(q.has_filters)

    def test_site_operator_case_insensitive(self):
        q = SearchQuery.parse("site:Example.COM test")
        self.assertEqual(q.site, "example.com")

    def test_tld_operator(self):
        q = SearchQuery.parse("tld:co.uk search")
        self.assertEqual(q.tld, "co.uk")
        self.assertEqual(q.clean_query, "search")

    def test_inurl_operator(self):
        q = SearchQuery.parse("inurl:download software")
        self.assertEqual(q.inurl, "download")
        self.assertEqual(q.clean_query, "software")

    def test_filetype_operator(self):
        q = SearchQuery.parse("filetype:pdf machine learning")
        self.assertEqual(q.filetype, "pdf")
        self.assertEqual(q.clean_query, "machine learning")

    def test_language_operator(self):
        q = SearchQuery.parse("LANGUAGE:zh 上海科技大学")
        self.assertEqual(q.language, "zh")
        self.assertEqual(q.clean_query, "上海科技大学")

    def test_protocol_operator(self):
        q = SearchQuery.parse("/ftp open source")
        self.assertEqual(q.protocol, "ftp")
        self.assertEqual(q.clean_query, "open source")

    def test_protocol_https(self):
        q = SearchQuery.parse("/https secure")
        self.assertEqual(q.protocol, "https")

    def test_author_operator(self):
        q = SearchQuery.parse("author:Einstein relativity")
        self.assertEqual(q.author, "Einstein")
        self.assertEqual(q.clean_query, "relativity")

    def test_exclude_word(self):
        q = SearchQuery.parse("jaguar -car")
        self.assertEqual(q.clean_query, "jaguar")
        self.assertIn("car", q.exclude_words)

    def test_multiple_exclude_words(self):
        q = SearchQuery.parse("python -snake -monty")
        self.assertEqual(q.clean_query, "python")
        self.assertIn("snake", q.exclude_words)
        self.assertIn("monty", q.exclude_words)

    def test_near_operator(self):
        q = SearchQuery.parse("apache server NEAR")
        self.assertTrue(q.near)
        self.assertEqual(q.clean_query, "apache server")

    def test_recent_operator(self):
        q = SearchQuery.parse("news RECENT")
        self.assertTrue(q.recent)
        self.assertEqual(q.clean_query, "news")

    def test_date_on(self):
        q = SearchQuery.parse("on:2024/11/01 event")
        self.assertEqual(q.date_on, "2024/11/01")
        self.assertEqual(q.clean_query, "event")

    def test_date_range(self):
        q = SearchQuery.parse("from:2024/11/01 to:2025/11/01 report")
        self.assertEqual(q.date_from, "2024/11/01")
        self.assertEqual(q.date_to, "2025/11/01")
        self.assertEqual(q.clean_query, "report")

    def test_combined_operators(self):
        q = SearchQuery.parse("site:shanghaitech.edu.cn filetype:pdf ShanghaiTech University")
        self.assertEqual(q.site, "shanghaitech.edu.cn")
        self.assertEqual(q.filetype, "pdf")
        self.assertEqual(q.clean_query, "ShanghaiTech University")
        self.assertTrue(q.has_filters)

    def test_complex_combined(self):
        q = SearchQuery.parse("site:github.com inurl:issues /https LANGUAGE:en python NEAR")
        self.assertEqual(q.site, "github.com")
        self.assertEqual(q.inurl, "issues")
        self.assertEqual(q.protocol, "https")
        self.assertEqual(q.language, "en")
        self.assertTrue(q.near)
        self.assertEqual(q.clean_query, "python")

    def test_repr(self):
        q = SearchQuery.parse("site:shanghaitech.edu.cn filetype:pdf ShanghaiTech")
        r = repr(q)
        self.assertIn("site:shanghaitech.edu.cn", r)
        self.assertIn("filetype=pdf", r)


class TestFilterReferences(unittest.TestCase):
    """测试 SearchQuery.filter_references() 客户端侧过滤。"""

    def _make_ref(self, url: str, title: str = "", description: str = "") -> MagicMock:
        """创建模拟 DHTReference。"""
        ref = MagicMock()
        ref.url = url
        ref.title = title
        ref.description = description
        return ref

    def test_no_filters_returns_all(self):
        q = SearchQuery.parse("test query")
        refs = [self._make_ref("http://a.com"), self._make_ref("http://b.com")]
        result = q.filter_references(refs)
        self.assertEqual(len(result), 2)

    def test_site_filter(self):
        q = SearchQuery.parse("site:example.com test")
        refs = [
            self._make_ref("http://example.com/page1"),
            self._make_ref("http://other.com/page2"),
            self._make_ref("http://www.example.com/page3"),
        ]
        result = q.filter_references(refs)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].url, "http://example.com/page1")
        self.assertEqual(result[1].url, "http://www.example.com/page3")

    def test_site_filter_excludes_subdomains(self):
        """site:example.com 不匹配 sub.example.com（YaCy 行为）。"""
        q = SearchQuery.parse("site:example.com test")
        refs = [
            self._make_ref("http://example.com/page"),
            self._make_ref("http://sub.example.com/page"),
        ]
        result = q.filter_references(refs)
        self.assertEqual(len(result), 1)

    def test_tld_filter(self):
        q = SearchQuery.parse("tld:edu.cn test")
        refs = [
            self._make_ref("http://www.shanghaitech.edu.cn/main.htm"),
            self._make_ref("http://example.com/page"),
            self._make_ref("https://www.gov.cn/index.htm"),
        ]
        result = q.filter_references(refs)
        self.assertEqual(len(result), 1)
        self.assertIn("shanghaitech.edu.cn", result[0].url)

    def test_inurl_filter(self):
        q = SearchQuery.parse("inurl:download test")
        refs = [
            self._make_ref("http://example.com/download/setup.exe"),
            self._make_ref("http://example.com/about"),
        ]
        result = q.filter_references(refs)
        self.assertEqual(len(result), 1)
        self.assertIn("download", result[0].url)

    def test_filetype_filter(self):
        q = SearchQuery.parse("filetype:pdf test")
        refs = [
            self._make_ref("http://example.com/report.pdf"),
            self._make_ref("http://example.com/page.html"),
            self._make_ref("http://example.com/slides.PDF"),  # 大小写
        ]
        result = q.filter_references(refs)
        self.assertEqual(len(result), 2)

    def test_protocol_filter(self):
        q = SearchQuery.parse("/https test")
        refs = [
            self._make_ref("https://example.com/secure"),
            self._make_ref("http://example.com/plain"),
            self._make_ref("ftp://files.example.com/data"),
        ]
        result = q.filter_references(refs)
        self.assertEqual(len(result), 1)

    def test_exclude_words_filter(self):
        q = SearchQuery.parse("jaguar -car")
        refs = [
            self._make_ref("http://animal.com", title="Jaguar animal"),
            self._make_ref("http://car.com", title="Jaguar car review"),
            self._make_ref("http://nature.com", description="The jaguar is a big cat"),
        ]
        result = q.filter_references(refs)
        self.assertEqual(len(result), 2)
        # "Jaguar car review" 应被排除
        for r in result:
            self.assertNotIn("car", r.title.lower())

    def test_combined_filters(self):
        q = SearchQuery.parse("site:example.com filetype:pdf test")
        refs = [
            self._make_ref("http://example.com/report.pdf"),
            self._make_ref("http://example.com/page.html"),
            self._make_ref("http://other.com/report.pdf"),
        ]
        result = q.filter_references(refs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].url, "http://example.com/report.pdf")


class TestFilterLinks(unittest.TestCase):
    """测试 SearchQuery.filter_links() 客户端侧过滤。"""

    def test_no_filters_returns_all(self):
        q = SearchQuery.parse("test")
        links = ["http://a.com", "http://b.com"]
        self.assertEqual(q.filter_links(links), links)

    def test_site_filter_links(self):
        q = SearchQuery.parse("site:example.com test")
        links = [
            "http://example.com/page",
            "http://other.com/page",
            "http://www.example.com/page",
        ]
        result = q.filter_links(links)
        self.assertEqual(len(result), 2)

    def test_filetype_filter_links(self):
        q = SearchQuery.parse("filetype:pdf test")
        links = [
            "http://example.com/report.pdf",
            "http://example.com/page.html",
        ]
        result = q.filter_links(links)
        self.assertEqual(len(result), 1)
        self.assertIn(".pdf", result[0])


class TestMatchHelpers(unittest.TestCase):
    """测试内部匹配工具方法。"""

    def test_match_site_exact(self):
        self.assertTrue(SearchQuery._match_site("http://example.com/page", "example.com"))
        self.assertTrue(SearchQuery._match_site("http://www.example.com/page", "example.com"))
        self.assertFalse(SearchQuery._match_site("http://sub.example.com/page", "example.com"))
        self.assertFalse(SearchQuery._match_site("http://other.com/page", "example.com"))

    def test_match_tld(self):
        self.assertTrue(SearchQuery._match_tld("http://example.co.uk/page", "co.uk"))
        self.assertTrue(SearchQuery._match_tld("http://sub.example.co.uk/page", "co.uk"))
        self.assertFalse(SearchQuery._match_tld("http://example.com/page", "co.uk"))

    def test_match_filetype(self):
        self.assertTrue(SearchQuery._match_filetype("http://example.com/file.pdf", "pdf"))
        self.assertTrue(SearchQuery._match_filetype("http://example.com/file.PDF", "pdf"))
        self.assertFalse(SearchQuery._match_filetype("http://example.com/file.html", "pdf"))
        self.assertTrue(SearchQuery._match_filetype("http://example.com/download.php?file=report.pdf", "pdf"))


class TestIntitleInhtmlLinkParsing(unittest.TestCase):
    """测试 PYaCy 扩展操作符 intitle:/inhtml:/link: 的解析。"""

    def test_intitle_operator(self):
        q = SearchQuery.parse("intitle:python tutorial")
        self.assertEqual(q.intitle, "python")
        self.assertEqual(q.clean_query, "tutorial")
        self.assertTrue(q.has_filters)

    def test_inhtml_operator(self):
        q = SearchQuery.parse("inhtml:flask REST API")
        self.assertEqual(q.inhtml, "flask")
        self.assertEqual(q.clean_query, "REST API")
        self.assertTrue(q.has_filters)

    def test_link_operator(self):
        q = SearchQuery.parse("link:example.com news")
        self.assertEqual(q.link, "example.com")
        self.assertEqual(q.clean_query, "news")
        self.assertTrue(q.has_filters)

    def test_combined_with_standard_operators(self):
        q = SearchQuery.parse("site:github.com intitle:bug inhtml:fix /https LANGUAGE:en")
        self.assertEqual(q.site, "github.com")
        self.assertEqual(q.intitle, "bug")
        self.assertEqual(q.inhtml, "fix")
        self.assertEqual(q.protocol, "https")
        self.assertEqual(q.language, "en")
        self.assertEqual(q.clean_query, "")

    def test_intitle_case_insensitive(self):
        q = SearchQuery.parse("intitle:Python test")
        self.assertEqual(q.intitle, "python")

    def test_repr_shows_new_fields(self):
        q = SearchQuery.parse("intitle:hello inhtml:world link:example.com")
        r = repr(q)
        self.assertIn("intitle=hello", r)
        self.assertIn("inhtml=world", r)
        self.assertIn("link=example.com", r)


class TestIntitleInhtmlLinkFiltering(unittest.TestCase):
    """测试 intitle:/inhtml:/link: 的客户端侧过滤。"""

    def _make_ref(self, url: str, title: str = "", description: str = "") -> MagicMock:
        ref = MagicMock()
        ref.url = url
        ref.title = title
        ref.description = description
        return ref

    def test_intitle_filter(self):
        q = SearchQuery.parse("intitle:python test")
        refs = [
            self._make_ref("http://a.com", title="Python Tutorial"),
            self._make_ref("http://b.com", title="Java Guide"),
            self._make_ref("http://c.com", title="Learn Python Basics"),
        ]
        result = q.filter_references(refs)
        self.assertEqual(len(result), 2)
        for r in result:
            self.assertIn("python", r.title.lower())

    def test_intitle_filter_no_match(self):
        q = SearchQuery.parse("intitle:nonexistent test")
        refs = [
            self._make_ref("http://a.com", title="Python Tutorial"),
        ]
        result = q.filter_references(refs)
        self.assertEqual(len(result), 0)

    def test_inhtml_filter(self):
        q = SearchQuery.parse("inhtml:flask test")
        refs = [
            self._make_ref("http://a.com", title="Web", description="Flask is a micro framework"),
            self._make_ref("http://b.com", title="Web", description="Django is a full framework"),
            self._make_ref("http://c.com", title="Flask Guide", description="Learn Flask"),
        ]
        result = q.filter_references(refs)
        self.assertEqual(len(result), 2)

    def test_link_filter(self):
        q = SearchQuery.parse("link:example.com test")
        refs = [
            self._make_ref("http://example.com/page1"),
            self._make_ref("http://other.com/page2"),
            self._make_ref("http://sub.example.com/page3"),
        ]
        result = q.filter_references(refs)
        self.assertEqual(len(result), 2)

    def test_link_filter_links(self):
        q = SearchQuery.parse("link:example.com test")
        links = [
            "http://example.com/page",
            "http://other.com/page",
            "http://sub.example.com/page",
        ]
        result = q.filter_links(links)
        self.assertEqual(len(result), 2)

    def test_combined_intitle_and_site(self):
        q = SearchQuery.parse("site:example.com intitle:python test")
        refs = [
            self._make_ref("http://example.com/a", title="Python Docs"),
            self._make_ref("http://example.com/b", title="Java Docs"),
            self._make_ref("http://other.com/c", title="Python Guide"),
        ]
        result = q.filter_references(refs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].url, "http://example.com/a")


if __name__ == "__main__":
    unittest.main()
