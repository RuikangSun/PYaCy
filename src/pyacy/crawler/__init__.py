# -*- coding: utf-8 -*-
"""PYaCy 简易爬虫模块。

本模块提供了基础的网页爬取能力，用于：
- 抓取指定 URL 的网页内容
- 提取页面文本和链接
- 将爬取结果推送到本地索引

设计原则:
    - 纯 Python 标准库实现（urllib + html.parser）
    - 遵守 robots.txt 礼仪
    - 可配置的爬取深度和延迟
    - Agent 友好的接口设计（未来扩展）

使用示例::

    from pyacy.crawler import SimpleCrawler

    crawler = SimpleCrawler()
    result = crawler.fetch("https://example.com")
    print(result.title, len(result.text))

    # 递归爬取
    results = crawler.crawl("https://example.com", depth=2)
"""

from .basic import SimpleCrawler, CrawlResult

__all__ = [
    "SimpleCrawler",
    "CrawlResult",
]
