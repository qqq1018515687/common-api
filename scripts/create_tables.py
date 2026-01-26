#!/usr/bin/env python3
"""创建数据库表"""

import sys
import os

# 添加项目路径到 Python 路径
sys.path.insert(0, '/workspace/projects/src')

from storage.database.db import get_engine
from storage.database.shared.model import Base, Users, RateLimits, History

def create_tables():
    """创建所有表"""
    engine = get_engine()

    # 创建所有表
    Base.metadata.create_all(bind=engine)
    print("数据库表创建成功！")

    # 列出所有表
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"当前数据库中的表: {tables}")

if __name__ == "__main__":
    create_tables()
