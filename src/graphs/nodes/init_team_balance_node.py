from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from graphs.team_balance_state import InitTeamBalanceInput, InitTeamBalanceOutput
from storage.database.team_balance_init import init_team_balance_system, check_tables_exist


def init_team_balance_node(state: InitTeamBalanceInput, config: RunnableConfig, runtime: Runtime[Context]) -> InitTeamBalanceOutput:
    """
    title: 团队余额系统初始化
    desc: 初始化团队余额相关的数据库表（teams、team_members、team_consumption_records）
    integrations: 数据库
    """
    ctx = runtime.context

    try:
        action = state.action

        if action == "init":
            # 初始化系统
            result = init_team_balance_system()
        elif action == "check":
            # 检查表是否存在
            result = check_tables_exist()
        else:
            result = {
                "success": False,
                "message": f"未知操作类型: {action}"
            }

        return InitTeamBalanceOutput(result=result)

    except Exception as e:
        return InitTeamBalanceOutput(result={
            "success": False,
            "message": f"初始化失败: {str(e)}"
        })
