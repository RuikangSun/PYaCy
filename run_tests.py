#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PYaCy 测试运行脚本。

用法:
    python run_tests.py          # 运行所有测试
    python run_tests.py -k test  # 运行名称匹配的测试
"""

import sys
from pathlib import Path

# 确保项目根目录和源码目录在 Python 路径中
_PROJECT_ROOT = Path(__file__).parent
_SRC_DIR = _PROJECT_ROOT / "src"
_TESTS_DIR = _PROJECT_ROOT / "tests"

sys.path.insert(0, str(_SRC_DIR))
sys.path.insert(0, str(_TESTS_DIR))

import pytest

sys.exit(pytest.main([str(_TESTS_DIR), "-v", "--tb=short"]))
