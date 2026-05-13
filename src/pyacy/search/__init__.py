# -*- coding: utf-8 -*-
"""PYaCy 高级搜索语法模块。

本模块提供 YaCy 兼容的高级搜索语法解析和客户端侧过滤功能。

YaCy 标准操作符（https://yacy.net/operation/search-parameters/）：
    - ``site:domain`` — 限定域名
    - ``tld:tld`` — 限定顶级域名
    - ``inurl:phrase`` — URL 包含短语
    - ``filetype:ext`` — 限定文件扩展名
    - ``LANGUAGE:xx`` — 语言过滤/排序
    - ``/protocol`` — 协议过滤（/http, /https, /ftp 等）
    - ``author:name`` — 作者过滤
    - ``-word`` — 排除词
    - ``NEAR`` — 邻近搜索
    - ``RECENT`` — 优先近期结果
    - ``on:date`` — 指定日期
    - ``from:date`` / ``to:date`` — 日期范围

PYaCy 扩展操作符（客户端侧过滤）：
    - ``intitle:phrase`` — 标题必须包含短语
    - ``inhtml:phrase`` — 正文必须包含短语
    - ``link:domain`` — 链接到指定域名

使用示例::

    from pyacy.search import SearchQuery

    q = SearchQuery.parse("site:shanghaitech.edu.cn filetype:pdf ShanghaiTech University")
    print(q.clean_query)     # "ShanghaiTech University"
    print(q.site)            # "shanghaitech.edu.cn"
    print(q.filetype)        # "pdf"

    # intitle: 过滤
    q2 = SearchQuery.parse("intitle:python NEAR tutorial")
    print(q2.intitle)        # "python"

    # 在 DHT 搜索结果上应用客户端过滤
    filtered = q.filter_results(search_result)
"""

from .query_parser import SearchQuery

__all__ = ["SearchQuery"]
