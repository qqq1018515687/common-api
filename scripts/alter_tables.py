#!/usr/bin/env python3
"""更新数据库表结构"""

import sys
import os

# 添加项目路径到 Python 路径
sys.path.insert(0, '/workspace/projects/src')

from storage.database.db import get_engine, get_session
from sqlalchemy import text

def update_users_table():
    """更新 users 表结构"""
    engine = get_engine()
    db = get_session()

    try:
        # 添加新列
        alter_statements = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS user_id VARCHAR(64) UNIQUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(11) UNIQUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar VARCHAR(256)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS team_id VARCHAR(64)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS gold_credits INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS silver_credits INTEGER DEFAULT 999999999",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user'",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS tier VARCHAR(20) DEFAULT 'standard'",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_status VARCHAR(20) DEFAULT 'active'",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP",
            "ALTER TABLE history ADD COLUMN IF NOT EXISTS meta_data JSON"
        ]

        for statement in alter_statements:
            print(f"执行: {statement}")
            db.execute(text(statement))
            db.commit()

        # 创建索引
        index_statements = [
            "CREATE INDEX IF NOT EXISTS ix_users_phone ON users(phone)",
            "CREATE INDEX IF NOT EXISTS ix_users_team_id ON users(team_id)",
            "CREATE INDEX IF NOT EXISTS ix_users_role ON users(role)",
            "CREATE INDEX IF NOT EXISTS ix_users_tier ON users(tier)",
            "CREATE INDEX IF NOT EXISTS ix_users_account_status ON users(account_status)",
            "CREATE INDEX IF NOT EXISTS ix_users_created_at ON users(created_at)"
        ]

        for statement in index_statements:
            print(f"执行: {statement}")
            db.execute(text(statement))
            db.commit()

        print("表结构更新成功！")

    except Exception as e:
        db.rollback()
        print(f"更新失败: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    update_users_table()
