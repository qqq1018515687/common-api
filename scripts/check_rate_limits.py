#!/usr/bin/env python3
"""查看限流记录"""

import sys
import os

# 添加项目路径到 Python 路径
sys.path.insert(0, '/workspace/projects/src')

from storage.database.db import get_engine, get_session
from storage.database.shared.model import RateLimits
from datetime import datetime, timedelta

def check_rate_limits():
    """查看限流记录"""
    db = get_session()

    try:
        # 查询所有限流记录
        records = db.query(RateLimits).all()

        print(f"共找到 {len(records)} 条限流记录：\n")

        for record in records:
            print(f"手机号: {record.phone}")
            print(f"IP地址: {record.ip_address}")
            print(f"请求次数: {record.request_count}")
            print(f"首次请求: {record.first_request_at}")
            print(f"最后请求: {record.last_request_at}")
            print(f"是否封禁: {record.is_blocked}")
            print(f"封禁到期: {record.blocked_until}")
            print(f"创建时间: {record.created_at}")
            print("-" * 50)

    except Exception as e:
        print(f"查询失败: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_rate_limits()
