"""
数据库表创建工具
通过工作流调用创建团队余额相关的表
"""

import logging
from storage.database.db import get_engine
from sqlalchemy import text

logger = logging.getLogger(__name__)


def create_team_balance_tables():
    """
    创建团队余额相关的三张表

    Returns:
        dict: 创建结果
    """
    try:
        # 创建 teams 表
        create_teams_sql = """
        CREATE TABLE IF NOT EXISTS teams (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            description VARCHAR(255),
            balance INTEGER DEFAULT 0,
            total_consumed INTEGER DEFAULT 0,
            member_count INTEGER DEFAULT 0,
            status VARCHAR(20) DEFAULT 'active',
            settings JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS ix_teams_status ON teams(status);
        """

        # 创建 team_members 表
        create_team_members_sql = """
        CREATE TABLE IF NOT EXISTS team_members (
            id VARCHAR(64) PRIMARY KEY,
            team_id VARCHAR(64) NOT NULL,
            user_id VARCHAR(36) NOT NULL,
            role VARCHAR(20) DEFAULT 'member',
            total_consumed INTEGER DEFAULT 0,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS ix_team_members_team ON team_members(team_id);
        CREATE INDEX IF NOT EXISTS ix_team_members_user ON team_members(user_id);
        CREATE INDEX IF NOT EXISTS ix_team_members_role ON team_members(team_id, role);
        """

        # 创建 team_consumption_records 表
        create_team_consumption_records_sql = """
        CREATE TABLE IF NOT EXISTS team_consumption_records (
            id VARCHAR(64) PRIMARY KEY,
            team_id VARCHAR(64) NOT NULL,
            user_id VARCHAR(36) NOT NULL,
            amount BIGINT NOT NULL,
            balance_before BIGINT,
            balance_after BIGINT,
            operation_type VARCHAR(20) NOT NULL,
            related_id VARCHAR(64),
            description VARCHAR(255),
            metadata JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS ix_team_records_team_time ON team_consumption_records(team_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_team_records_user_time ON team_consumption_records(user_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_team_records_type ON team_consumption_records(team_id, operation_type);
        """

        with get_engine().connect() as conn:
            # 创建 teams 表
            conn.execute(text(create_teams_sql))
            logger.info("✅ teams 表创建成功")

            # 创建 team_members 表
            conn.execute(text(create_team_members_sql))
            logger.info("✅ team_members 表创建成功")

            # 创建 team_consumption_records 表
            conn.execute(text(create_team_consumption_records_sql))
            logger.info("✅ team_consumption_records 表创建成功")

        return {
            "success": True,
            "message": "所有表创建成功",
            "tables": ["teams", "team_members", "team_consumption_records"]
        }

    except Exception as e:
        logger.error(f"创建表失败: {e}")
        return {
            "success": False,
            "message": f"创建表失败: {str(e)}"
        }


def check_tables_exist():
    """
    检查团队余额相关的表是否存在

    Returns:
        dict: 检查结果
    """
    try:
        tables_to_check = ["teams", "team_members", "team_consumption_records"]
        result = {}

        with get_engine().connect() as conn:
            for table in tables_to_check:
                check_sql = f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = '{table}'
                );
                """
                exists = conn.execute(text(check_sql)).scalar()
                result[table] = bool(exists)

        all_exist = all(result.values())

        return {
            "success": True,
            "all_exist": all_exist,
            "tables": result
        }

    except Exception as e:
        logger.error(f"检查表失败: {e}")
        return {
            "success": False,
            "message": f"检查表失败: {str(e)}"
        }


def init_team_balance_system():
    """
    初始化团队余额系统
    1. 检查表是否存在
    2. 如果不存在，创建表

    Returns:
        dict: 初始化结果
    """
    try:
        # 检查表是否存在
        check_result = check_tables_exist()

        if not check_result.get("success"):
            return {
                "success": False,
                "message": "检查表失败"
            }

        if check_result.get("all_exist"):
            return {
                "success": True,
                "message": "团队余额系统已初始化，表已存在",
                "tables": check_result.get("tables")
            }

        # 创建表
        create_result = create_team_balance_tables()

        if create_result.get("success"):
            return {
                "success": True,
                "message": "团队余额系统初始化成功",
                "tables_created": create_result.get("tables")
            }
        else:
            return create_result

    except Exception as e:
        logger.error(f"初始化团队余额系统失败: {e}")
        return {
            "success": False,
            "message": f"初始化失败: {str(e)}"
        }


if __name__ == "__main__":
    # 测试：直接运行脚本
    result = init_team_balance_system()
    print(result)
