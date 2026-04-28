#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PYaCy 测试运行脚本。

用法:
    python run_tests.py                        # 运行所有单元测试
    python run_tests.py --live                 # 包含线上连通性测试（慢）
    python run_tests.py -k test_seed           # 运行名称匹配的测试
    python run_tests.py --live --connectivity-only  # 仅连通性测试
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


def main() -> int:
    """解析参数并运行测试。"""
    args = sys.argv[1:]

    # 检查是否包含线上测试
    run_live = "--live" in args
    if run_live:
        args.remove("--live")

    # 默认排除线上测试（太慢且需要网络）
    if not run_live:
        args.extend([
            "--ignore=tests/test_live_network.py",
        ])

    # 添加默认参数
    default_args = [
        str(_TESTS_DIR),
        "-v",
        "--tb=short",
    ]

    # 合并参数（用户参数优先）
    for a in default_args:
        if a not in args and not any(
            a.startswith(x) for x in ["--ignore", "-k", "-x", "-q"]
        ):
            args.insert(0, a)

    return pytest.main(args)


if __name__ == "__main__":
    sys.exit(main())
