#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PYaCy Level 2 示例 - P2P 节点发现与 DHT 搜索。

本示例演示如何使用 PYaCy 的 Level 2 功能：
1. 创建 P2P 节点
2. 连接到已知种子节点
3. 执行 DHT 分布式搜索
4. 查看网络统计信息
"""

import sys
from pathlib import Path

# 确保可以导入 pyacy
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyacy import PYaCyNode, Seed
from pyacy.p2p.seed import PEERTYPE_SENIOR


def main():
    """Level 2 示例主函数。"""
    print("=" * 60)
    print("PYaCy Level 2 示例 - P2P 节点发现与 DHT 搜索")
    print("=" * 60)

    # 1. 创建 P2P 节点
    print("\n[1] 创建 P2P 节点...")
    node = PYaCyNode(name="my-pyacy-node")
    print(f"    节点名称：{node.name}")
    print(f"    节点哈希：{node.hash}")
    print(f"    节点类型：Junior (默认)")
    print(f"    当前节点数：{node.peer_count}")

    # 2. 添加已知种子节点
    print("\n[2] 添加已知种子节点...")
    # 模拟添加一个 Senior 节点
    senior_seed_str = Seed.create_junior("simulated-senior").to_seed_string()
    seed = node.add_peer("http://10.0.0.1:8090", senior_seed_str)
    if seed:
        print(f"    成功添加节点：{seed.name}")
        print(f"    节点哈希：{seed.hash}")
        print(f"    节点类型：{seed.peer_type}")

    # 3. 查看节点统计
    print("\n[3] 网络统计信息:")
    stats = node.get_peer_stats()
    print(f"    总节点数：{stats['total_peers']}")
    print(f"    Senior 节点数：{stats['senior_peers']}")
    print(f"    已引导：{stats['is_bootstrapped']}")
    print(f"    节点类型分布：{stats.get('type_distribution', {})}")

    # 4. 尝试搜索（需要真实连接）
    print("\n[4] DHT 搜索示例:")
    print("    注意：实际搜索需要连接到真实的 YaCy P2P 网络")
    print("    以下展示搜索 API 调用方式:")
    print('    >>> results = node.search("hello world")')
    print("    >>> for ref in results.references:")
    print("    ...     print(ref.url)")

    # 5. 清理
    print("\n[5] 清理资源...")
    node.close()
    print("    节点已关闭")

    print("\n" + "=" * 60)
    print("示例完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
