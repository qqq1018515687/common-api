"""
团队初始化节点
负责初始化团队余额相关的数据库表
"""
import logging
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from graphs.team_balance_state import TeamInitInput, TeamInitOutput
from storage.database.team_balance_init import init_team_balance_system, check_tables_exist

logger = logging.getLogger(__name__)


def team_init_node(state: TeamInitInput, config: RunnableConfig, runtime: Runtime[Context]) -> TeamInitOutput:
    """
    title: 团队系统初始化
    desc: 初始化团队余额相关的数据库表（teams、team_members、team_consumption_records）
    integrations: 数据库
    """
    ctx = runtime.context
    action = state.action

    try:
        if action == "init":
            result = init_team_balance_system()
        elif action == "check":
            result = check_tables_exist()
        else:
            result = {
                "success": False,
                "message": f"未知操作类型: {action}"
            }

        return TeamInitOutput(
            response_data={
                "code": 0 if result.get("success") else 1,
                "msg": result.get("message", ""),
                "data": result
            }
        )

    except Exception as e:
        logger.error(f"团队系统初始化失败: {e}")
        return TeamInitOutput(
            response_data={
                "code": 1,
                "msg": f"初始化失败: {str(e)}",
                "data": {}
            }
        )
