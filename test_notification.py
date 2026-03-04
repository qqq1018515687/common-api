#!/usr/bin/env python3
"""测试系统通知功能 - 直接操作生产数据库"""
import sys
import os
import time

# 添加 src 目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from storage.database.db import get_session
from storage.database.shared.model import SystemNotifications


def test_create_notification():
    """测试创建通知"""
    db = get_session()

    try:
        print("=" * 60)
        print("测试系统通知功能")
        print("=" * 60)

        # 检查表是否存在
        print("\n1. 检查 system_notifications 表是否存在...")
        from sqlalchemy import text
        result = db.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'system_notifications')"))
        table_exists = result.fetchone()[0]

        if not table_exists:
            print("❌ 表不存在！请先运行: alembic upgrade head")
            return False

        print("✅ 表存在")

        # 查看当前表中的数据
        print("\n2. 查看当前表中的数据...")
        from sqlalchemy import text
        result = db.execute(text("SELECT COUNT(*) FROM system_notifications"))
        count = result.fetchone()[0]
        print(f"   当前通知数量: {count}")

        if count > 0:
            print("\n   现有通知列表:")
            result = db.execute(text("SELECT id, type, title, priority, is_active, created_at FROM system_notifications ORDER BY created_at DESC LIMIT 10"))
            for row in result:
                print(f"   - ID: {row[0]}, 类型: {row[1]}, 标题: {row[2]}, 优先级: {row[3]}, 激活: {row[4]}, 创建时间: {row[5]}")

        # 创建测试通知
        print("\n3. 创建测试通知...")
        current_time = int(time.time() * 1000)

        test_notification = SystemNotifications(
            id=f"test_{current_time}",
            type="info",
            title="测试通知 - 生产环境",
            content="<p>这是一条在生产环境创建的测试通知</p><p>用于验证系统通知功能是否正常工作</p>",
            priority="medium",
            is_active=True,
            start_time=current_time,
            end_time=None,  # 永久有效
            dismissible=True,
            link_url="https://example.com",
            target_audience="all",
            created_at=current_time,
            updated_at=current_time,
            created_by="test_admin_001"
        )

        db.add(test_notification)
        db.commit()
        db.refresh(test_notification)

        print(f"✅ 测试通知创建成功！")
        print(f"   ID: {test_notification.id}")
        print(f"   标题: {test_notification.title}")
        print(f"   创建时间: {test_notification.created_at}")

        # 查询验证
        print("\n4. 查询验证...")
        from sqlalchemy import text
        result = db.execute(text(f"SELECT * FROM system_notifications WHERE id = '{test_notification.id}'"))
        row = result.fetchone()

        if row:
            print("✅ 查询成功，通知已保存到数据库")
            print(f"   数据行数: {len(row)} 字段")
        else:
            print("❌ 查询失败，未找到通知")
            return False

        # 查询有效通知
        print("\n5. 查询当前有效的通知...")
        result = db.execute(text("""
            SELECT id, type, title, priority, is_active, start_time, end_time
            FROM system_notifications
            WHERE is_active = true
            AND start_time <= :current_time
            AND (end_time >= :current_time OR end_time IS NULL)
            ORDER BY priority DESC, created_at DESC
        """), {"current_time": current_time + 1000})

        active_count = result.rowcount
        print(f"✅ 有效通知数量: {active_count}")

        if active_count > 0:
            print("\n   有效通知列表:")
            for row in result:
                print(f"   - ID: {row[0]}, 类型: {row[1]}, 标题: {row[2]}, 优先级: {row[3]}")

        print("\n" + "=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        db.close()


if __name__ == "__main__":
    success = test_create_notification()
    sys.exit(0 if success else 1)
