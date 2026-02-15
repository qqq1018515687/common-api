#!/usr/bin/env python3.12
"""测试头像更新功能"""

import os
import sys

# 设置环境变量
os.environ['COZE_WORKSPACE_PATH'] = '/workspace/projects'

# 设置 Python 路径
sys.path.insert(0, '/workspace/projects/src')
sys.path.insert(0, '/workspace/projects')

print("============================================================")
print("头像更新功能测试")
print("============================================================")

# 测试 1: 导入所有模块
print("\n[测试 1] 导入所有模块...")
try:
    from langchain_core.exceptions import ContextOverflowError
    print("✓ langchain_core.exceptions.ContextOverflowError 导入成功")
except Exception as e:
    print(f"✗ ContextOverflowError 导入失败: {e}")

try:
    from coze_coding_dev_sdk import LLMClient
    print("✓ coze_coding_dev_sdk.LLMClient 导入成功")
except Exception as e:
    print(f"✗ LLMClient 导入失败: {e}")

try:
    from graphs.node import update_user_node
    print("✓ graphs.node.update_user_node 导入成功")
except Exception as e:
    print(f"✗ update_user_node 导入失败: {e}")

try:
    from graphs.graph import main_graph
    print("✓ graphs.graph.main_graph 导入成功")
except Exception as e:
    print(f"✗ main_graph 导入失败: {e}")

print("\n所有模块导入完成！")
print("============================================================")
