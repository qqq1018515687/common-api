#!/usr/bin/env python3
"""检查数据库表结构"""

import sys
import os

# 添加项目路径到 Python 路径
sys.path.insert(0, '/workspace/projects/src')

from storage.database.db import get_engine
from sqlalchemy import inspect

def check_tables():
    """检查所有表结构"""
    engine = get_engine()
    inspector = inspect(engine)

    # 获取所有表名
    tables = inspector.get_table_names()
    print(f"当前数据库中的表: {tables}\n")

    # 检查每个表的结构
    for table_name in tables:
        print(f"=== 表: {table_name} ===")
        columns = inspector.get_columns(table_name)
        for col in columns:
            print(f"  - {col['name']}: {col['type']} (nullable: {col['nullable']}, default: {col['default']})")
        print()

if __name__ == "__main__":
    check_tables()
