"""
系统初始化API接口
用于初始化数据库表等功能
"""

from fastapi import APIRouter, HTTPException
import logging

from storage.database.team_balance_init import init_team_balance_system, check_tables_exist

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["系统初始化"])


@router.post("/init/team-balance")
async def init_team_balance():
    """
    初始化团队余额系统

    自动创建团队余额相关的数据库表：
    - teams（团队信息表）
    - team_members（团队成员表）
    - team_consumption_records（消费记录表）

    Returns:
        初始化结果
    """
    try:
        logger.info("开始初始化团队余额系统...")

        result = init_team_balance_system()

        if result.get("success"):
            logger.info(f"团队余额系统初始化成功: {result}")
            return result
        else:
            logger.error(f"团队余额系统初始化失败: {result}")
            raise HTTPException(status_code=500, detail=result.get("message"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"初始化团队余额系统异常: {e}")
        raise HTTPException(status_code=500, detail=f"初始化失败: {str(e)}")


@router.get("/check/tables")
async def check_tables():
    """
    检查团队余额相关的表是否存在

    Returns:
        检查结果
    """
    try:
        result = check_tables_exist()

        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=500, detail=result.get("message"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"检查表异常: {e}")
        raise HTTPException(status_code=500, detail=f"检查失败: {str(e)}")
