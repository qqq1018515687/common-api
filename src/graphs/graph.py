import logging
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from pydantic import BaseModel, Field
from typing import Optional

logger = logging.getLogger(__name__)

from graphs.state import (
    GlobalState,
    GraphInput,
    GraphOutput,
    UploadInput,
    SaveInput,
    FormatResponseInput,
    RouterInput,
    RouterOutput,
    OperationRouteInput,
    OperationRouteOutput,
    ToolRouteInput,
    ToolRouteOutput,
    UnpackInputDataInput,
    UnpackInputDataOutput,
    SystemNotificationInput,
    SystemNotificationOutput,
    AnnouncementInput,
    AnnouncementOutput,
    CheckNeedTagsOutput
)
from graphs.node import (
    upload_node,
    delete_upload_node,
    save_node,
    format_response_node,
    router_node,
    operation_route_node,
    route_by_operation_type,
    tool_route_node,
    reverse_image_node,
    translate_doubao_node,
    prompt_enhance_node,
    unpack_input_data_node,
    check_rate_limit_node,
    create_user_node,
    update_rate_limit_node,
    send_register_code_node,
    send_password_reset_code_node,
    register_with_limit_node,
    register_with_code_node,
    reset_password_with_code_node,
    get_user_node,
    get_user_by_id_node,
    update_user_node,
    delete_user_node,
    list_users_node,
    task_route_node,
    route_by_task_operation_type,
    create_task_node,
    update_task_node,
    delete_task_node,
    list_tasks_node
)
from graphs.nodes.system_notification_handler_node import system_notification_handler_node
from graphs.nodes.announcement_handler_node import announcement_handler_node
from graphs.nodes.image_tagging_node import image_tagging_node
from graphs.nodes.save_image_tags_node import save_image_tags_node
from graphs.nodes.check_need_tags_node import check_need_tags_node
from graphs.nodes.team_route_node import team_route_node, route_by_team_operation_type
from graphs.nodes.team_init_node import team_init_node
from graphs.nodes.team_manage_node import team_manage_node
from graphs.nodes.team_recharge_node import team_recharge_node
from graphs.nodes.team_deduct_node import team_deduct_node
from graphs.nodes.team_refund_node import team_refund_node
from graphs.nodes.team_records_node import team_records_node
from graphs.nodes.runninghub_error_analysis_node import runninghub_error_analysis_node
from graphs.nodes.agent_intent_node import agent_intent_node
from graphs.nodes.agent_run_node import agent_run_node
from graphs.nodes.billing_route_node import billing_route_node, route_by_billing_operation_type
from graphs.nodes.get_balance_node import get_balance_node
from graphs.nodes.billing_deduct_node import billing_deduct_node
from graphs.nodes.billing_refund_node import billing_refund_node
from graphs.nodes.billing_settle_node import billing_settle_node
from graphs.nodes.billing_records_node import billing_records_node
from graphs.nodes.storage_management_node import storage_management_node


def route_by_call_type(state: RouterOutput) -> str:
    """
    title: 根据调用类型路由
    desc: 根据 call_type 参数将请求路由到不同的处理节点
    """
    call_type = state.call_type

    if call_type == "account_management":
        return "账号管理"
    elif call_type == "upload":
        return "文件上传"
    elif call_type == "delete_upload":
        return "删除上传文件"
    elif call_type == "storage_management":
        return "对象储存管理"
    elif call_type == "save":
        return "保存历史"
    elif call_type == "task_management" or call_type == "user_task_management" or call_type == "list_tasks":
        return "任务管理"
    elif call_type == "tool":
        return "工具中心"
    elif call_type == "notification_management":
        return "通知管理"
    elif call_type == "announcement_management":
        return "公告管理"
    elif call_type == "team_balance":
        return "团队余额"
    elif call_type == "runninghub_error_analysis":
        return "RunningHub错误分析"
    elif call_type == "agent_intent":
        return "Agent意图判断"
    elif call_type == "agent_run":
        return "Agent Run"
    elif call_type == "billing":
        return "资金扣费"
    else:
        return "账号管理"  # 默认


def route_by_tool_type(state: ToolRouteOutput) -> str:
    """
    title: 根据工具类型路由
    desc: 根据 tool_type 参数将请求路由到具体的工具节点
    """
    tool_type = state.tool_type

    if tool_type == "reverse_image":
        return "反推图像"
    elif tool_type == "translate_doubao":
        return "翻译推荐"
    elif tool_type == "translate_flash":
        return "翻译推荐"
    elif tool_type == "prompt_enhance":
        return "提示词增强"
    else:
        return "反推图像"


def route_by_need_tags(state: CheckNeedTagsOutput) -> str:
    """
    title: 是否需要生成标签
    desc: 根据任务状态和结果判断是否需要生成图像标签
    """
    if state.need_tags:
        return "生成标签"
    else:
        return "直接返回"




# 创建状态图，指定图的入参和出参
builder = StateGraph(GlobalState, input_schema=GraphInput, output_schema=GraphOutput)

# 添加节点
builder.add_node("unpack_input_data", unpack_input_data_node)
builder.add_node("call_type_router", router_node)
builder.add_node("operation_route", operation_route_node)
builder.add_node("check_rate_limit", check_rate_limit_node)
builder.add_node("update_rate_limit", update_rate_limit_node)
builder.add_node("send_register_code", send_register_code_node)
builder.add_node("send_password_reset_code", send_password_reset_code_node)
builder.add_node("register_with_limit", register_with_limit_node)
builder.add_node("register_with_code", register_with_code_node)
builder.add_node("reset_password_with_code", reset_password_with_code_node)
builder.add_node("get_user", get_user_node)
builder.add_node("get_user_by_id", get_user_by_id_node)
builder.add_node("update_user", update_user_node)
builder.add_node("delete_user", delete_user_node)
builder.add_node("list_users", list_users_node)
builder.add_node("upload", upload_node)
builder.add_node("delete_upload", delete_upload_node)
builder.add_node("storage_management", storage_management_node)
builder.add_node("save", save_node)
builder.add_node("task_route", task_route_node)
builder.add_node("create_task", create_task_node)
builder.add_node("update_task", update_task_node)
builder.add_node("delete_task", delete_task_node)
builder.add_node("list_tasks", list_tasks_node)
builder.add_node("system_notification_handler", system_notification_handler_node)
builder.add_node("announcement_handler", announcement_handler_node)
builder.add_node("format_response", format_response_node)
builder.add_node("check_need_tags", check_need_tags_node)
builder.add_node("image_tagging", image_tagging_node, metadata={"type": "agent", "llm_cfg": "config/image_tagging_cfg.json"})
builder.add_node("save_image_tags", save_image_tags_node)
builder.add_node("tool_route", tool_route_node)
builder.add_node("reverse_image", reverse_image_node, metadata={"type": "agent", "llm_cfg": "config/reverse_image_cfg.json"})
builder.add_node("translate_doubao", translate_doubao_node, metadata={"type": "agent", "llm_cfg": "config/translate_doubao_cfg.json"})
builder.add_node("prompt_enhance", prompt_enhance_node, metadata={"type": "agent", "llm_cfg": "config/prompt_enhance_cfg.json"})
builder.add_node("team_route", team_route_node)
builder.add_node("team_init", team_init_node)
builder.add_node("team_manage", team_manage_node)
builder.add_node("team_recharge", team_recharge_node)
builder.add_node("team_deduct", team_deduct_node)
builder.add_node("team_refund", team_refund_node)
builder.add_node("team_records", team_records_node)
builder.add_node("runninghub_error_analysis", runninghub_error_analysis_node, metadata={"type": "agent", "llm_cfg": "config/runninghub_error_analysis_cfg.json"})
builder.add_node("agent_intent", agent_intent_node, metadata={"type": "agent", "llm_cfg": "config/agent_intent_cfg.json"})
builder.add_node("agent_run", agent_run_node)
builder.add_node("billing_route", billing_route_node)
builder.add_node("get_balance", get_balance_node)
builder.add_node("billing_deduct", billing_deduct_node)
builder.add_node("billing_refund", billing_refund_node)
builder.add_node("billing_settle", billing_settle_node)
builder.add_node("billing_records", billing_records_node)

# 设置入口点（先解包数据）
builder.set_entry_point("unpack_input_data")

# 解包后进入路由节点
builder.add_edge("unpack_input_data", "call_type_router")

# 添加一级条件分支（根据 call_type）
builder.add_conditional_edges(
    source="call_type_router",
    path=route_by_call_type,
    path_map={
        "账号管理": "operation_route",
        "文件上传": "upload",
        "删除上传文件": "delete_upload",
        "对象储存管理": "storage_management",
        "保存历史": "save",
        "任务管理": "task_route",
        "工具中心": "tool_route",
        "通知管理": "system_notification_handler",
        "公告管理": "announcement_handler",
        "团队余额": "team_route",  # 路由到团队余额路由节点
        "RunningHub错误分析": "runninghub_error_analysis",
        "Agent意图判断": "agent_intent",
        "Agent Run": "agent_run",
        "资金扣费": "billing_route"
    }
)

# 添加二级条件分支（根据 tool_type）
builder.add_conditional_edges(
    source="tool_route",
    path=route_by_tool_type,
    path_map={
        "反推图像": "reverse_image",
        "翻译推荐": "translate_doubao",
        "提示词增强": "prompt_enhance"
    }
)

# 添加二级条件分支（根据 operation_type）
builder.add_conditional_edges(
    source="operation_route",
    path=route_by_operation_type,
    path_map={
        "限流检查": "check_rate_limit",
        "更新限流": "update_rate_limit",
        "发送注册验证码": "send_register_code",
        "发送密码重置验证码": "send_password_reset_code",
        "用户注册": "register_with_limit",
        "验证码注册": "register_with_code",
        "验证码重置密码": "reset_password_with_code",
        "用户登录": "get_user",
        "查询单个用户": "get_user_by_id",
        "更新用户": "update_user",
        "删除用户": "delete_user",
        "用户列表": "list_users"
    }
)

# 添加任务管理二级条件分支
builder.add_conditional_edges(
    source="task_route",
    path=route_by_task_operation_type,
    path_map={
        "创建任务": "create_task",
        "更新任务": "update_task",
        "删除任务": "delete_task",
        "查询任务列表": "list_tasks"
    }
)

# 添加团队余额二级条件分支
builder.add_conditional_edges(
    source="team_route",
    path=route_by_team_operation_type,
    path_map={
        "初始化团队": "team_init",
        "团队管理": "team_manage",
        "团队充值": "team_recharge",
        "团队扣费": "team_deduct",
        "团队退款": "team_refund",
        "消费记录": "team_records"
    }
    )

# 添加资金扣费二级条件分支
builder.add_conditional_edges(
    source="billing_route",
    path=route_by_billing_operation_type,
    path_map={
        "查询余额": "get_balance",
        "扣费": "billing_deduct",
        "退款": "billing_refund",
        "结算": "billing_settle",
        "账单记录": "billing_records"
    }
)

# 各业务分支汇聚到统一返回节点
builder.add_edge("check_rate_limit", "format_response")
builder.add_edge("update_rate_limit", "format_response")
builder.add_edge("send_register_code", "format_response")
builder.add_edge("send_password_reset_code", "format_response")
builder.add_edge("register_with_limit", "format_response")
builder.add_edge("register_with_code", "format_response")
builder.add_edge("reset_password_with_code", "format_response")
builder.add_edge("get_user", "format_response")
builder.add_edge("get_user_by_id", "format_response")
builder.add_edge("update_user", "format_response")
builder.add_edge("delete_user", "format_response")
builder.add_edge("list_users", "format_response")
builder.add_edge("upload", "format_response")
builder.add_edge("delete_upload", "format_response")
builder.add_edge("storage_management", "format_response")
builder.add_edge("save", "format_response")
builder.add_edge("create_task", "format_response")
builder.add_edge("update_task", "format_response")  # 暂时禁用图像自动打标，直接返回
builder.add_edge("delete_task", "format_response")
builder.add_edge("list_tasks", "format_response")
builder.add_edge("system_notification_handler", "format_response")
builder.add_edge("announcement_handler", "format_response")
builder.add_edge("reverse_image", "format_response")
builder.add_edge("translate_doubao", "format_response")
builder.add_edge("prompt_enhance", "format_response")
builder.add_edge("team_init", "format_response")
builder.add_edge("team_manage", "format_response")
builder.add_edge("team_recharge", "format_response")
builder.add_edge("team_deduct", "format_response")
builder.add_edge("team_refund", "format_response")
builder.add_edge("team_records", "format_response")
builder.add_edge("runninghub_error_analysis", "format_response")
builder.add_edge("agent_intent", "format_response")
builder.add_edge("agent_run", "format_response")
builder.add_edge("get_balance", "format_response")
builder.add_edge("billing_deduct", "format_response")
builder.add_edge("billing_refund", "format_response")
builder.add_edge("billing_settle", "format_response")
builder.add_edge("billing_records", "format_response")

# ============ 图像标签生成流程（暂时禁用）============
# 启用图像自动打标时，取消下面的注释，并注释掉上面的 `builder.add_edge("update_task", "format_response")`
#
# builder.add_edge("update_task", "check_need_tags")
# builder.add_conditional_edges(
#     source="check_need_tags",
#     path=route_by_need_tags,
#     path_map={
#         "生成标签": "image_tagging",
#         "直接返回": "format_response"
#     }
# )
# builder.add_edge("image_tagging", "save_image_tags")
# builder.add_edge("save_image_tags", "format_response")

# 统一返回节点到结束
builder.add_edge("format_response", END)

# 编译图
main_graph = builder.compile()
