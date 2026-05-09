# -*- coding: utf-8 -*-
"""PYaCy API 适配器模块。

本模块提供统一的 API 接口，用于：
- GUI 应用调用
- Agent 智能体调用
- 外部程序集成

设计原则:
    - 统一的搜索接口（本地 + 远程并行）
    - 简洁的数据模型（dict/list）
    - 预留 Agent 友好的扩展接口
    - 与核心模块解耦

使用示例::

    from pyacy.api import PYaCyAdapter

    adapter = PYaCyAdapter()
    adapter.bootstrap()

    # 统一搜索接口
    results = adapter.search("python tutorial")

    # 本地 RWI 统计
    rwi_stats = adapter.get_rwi_stats()

    # 本地索引统计
    index_stats = adapter.get_index_stats()
"""

from .adapter import PYaCyAdapter

__all__ = ["PYaCyAdapter"]