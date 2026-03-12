"""
用户数据迁移脚本：将现有用户迁移到团队系统
方案：每个用户创建独立团队，自己作为管理员
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import uuid
from datetime import datetime
from sqlalchemy import select
from storage.database.db import get_session
from storage.database.shared.model import Users, Teams, TeamMembers


def migrate_users_to_teams():
    """
    将现有用户迁移到团队系统
    - 为每个用户创建独立团队
    - 用户作为团队管理员
    """
    session = get_session()
    
    try:
        # 1. 查询所有用户
        users = session.scalars(select(Users)).all()
        print(f"📊 找到 {len(users)} 个用户")
        
        if not users:
            print("❌ 没有用户需要迁移")
            return
        
        # 2. 为每个用户创建团队
        created_count = 0
        skipped_count = 0
        
        for user in users:
            # 检查用户是否已有团队
            existing_member = session.scalar(
                select(TeamMembers).where(TeamMembers.user_id == user.id)
            )
            
            if existing_member:
                print(f"⏭️  用户 {user.username} 已在团队中，跳过")
                skipped_count += 1
                continue
            
            # 创建团队
            team_id = str(uuid.uuid4())
            team = Teams(
                id=team_id,
                name=f"{user.username} 的团队",
                description=f"用户 {user.username} 的个人团队",
                balance=0,  # 初始余额为0
                total_consumed=0,
                member_count=1,
                status='active',
                settings={}
            )
            session.add(team)
            
            # 将用户添加为管理员
            member_id = str(uuid.uuid4())
            member = TeamMembers(
                id=member_id,
                team_id=team_id,
                user_id=user.id,
                role='admin',
                total_consumed=0
            )
            session.add(member)
            
            # 更新用户的 team_id（如果 users 表有这个字段）
            if hasattr(user, 'team_id'):
                user.team_id = team_id
            
            print(f"✅ 为用户 {user.username} 创建团队: {team.name}")
            created_count += 1
        
        # 3. 提交事务
        session.commit()
        
        print(f"\n🎉 迁移完成！")
        print(f"   ✅ 创建团队: {created_count} 个")
        print(f"   ⏭️  跳过用户: {skipped_count} 个")
        
        # 4. 验证结果
        total_teams = session.scalar(select(Teams))
        total_members = session.scalar(select(TeamMembers))
        print(f"\n📊 当前数据：")
        print(f"   团队总数: {session.query(Teams).count()}")
        print(f"   成员总数: {session.query(TeamMembers).count()}")
        
    except Exception as e:
        session.rollback()
        print(f"❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


def check_migration_status():
    """检查迁移状态"""
    session = get_session()
    
    try:
        total_users = session.query(Users).count()
        users_with_team = session.query(TeamMembers).count()
        users_without_team = total_users - users_with_team
        
        print(f"📊 迁移状态：")
        print(f"   总用户数: {total_users}")
        print(f"   已加入团队: {users_with_team}")
        print(f"   未加入团队: {users_without_team}")
        
        if users_without_team > 0:
            print(f"\n⚠️  还有 {users_without_team} 个用户未加入团队")
            print("   运行 migrate_users_to_teams() 进行迁移")
        else:
            print(f"\n✅ 所有用户都已加入团队")
            
    finally:
        session.close()


if __name__ == "__main__":
    print("=" * 50)
    print("用户数据迁移脚本")
    print("=" * 50)
    
    # 1. 先检查状态
    print("\n1️⃣  检查当前状态...")
    check_migration_status()
    
    # 2. 确认执行
    print("\n" + "=" * 50)
    confirm = input("是否开始迁移？(yes/no): ").strip().lower()
    
    if confirm == 'yes':
        print("\n2️⃣  开始迁移...")
        migrate_users_to_teams()
        
        print("\n3️⃣  验证结果...")
        check_migration_status()
    else:
        print("❌ 已取消迁移")
