from langgraph.graph import StateGraph, END
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
    UnpackInputDataOutput
)
from graphs.node import (
    upload_node,
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
    register_with_limit_node,
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
    elif call_type == "save":
        return "保存历史"
    elif call_type == "user_task_management":
        return "任务管理"
    elif call_type == "tool":
        return "工具中心"
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


# 创建状态图，指定图的入参和出参
builder = StateGraph(GlobalState, input_schema=GraphInput, output_schema=GraphOutput)

# 添加节点
builder.add_node("unpack_input_data", unpack_input_data_node)
builder.add_node("call_type_router", router_node)
builder.add_node("operation_route", operation_route_node)
builder.add_node("check_rate_limit", check_rate_limit_node)
builder.add_node("update_rate_limit", update_rate_limit_node)
builder.add_node("register_with_limit", register_with_limit_node)
builder.add_node("get_user", get_user_node)
builder.add_node("get_user_by_id", get_user_by_id_node)
builder.add_node("update_user", update_user_node)
builder.add_node("delete_user", delete_user_node)
builder.add_node("list_users", list_users_node)
builder.add_node("upload", upload_node)
builder.add_node("save", save_node)
builder.add_node("task_route", task_route_node)
builder.add_node("create_task", create_task_node)
builder.add_node("update_task", update_task_node)
builder.add_node("delete_task", delete_task_node)
builder.add_node("list_tasks", list_tasks_node)
builder.add_node("format_response", format_response_node)
builder.add_node("tool_route", tool_route_node)
builder.add_node("reverse_image", reverse_image_node, metadata={"type": "agent", "llm_cfg": "config/reverse_image_cfg.json"})
builder.add_node("translate_doubao", translate_doubao_node, metadata={"type": "agent", "llm_cfg": "config/translate_doubao_cfg.json"})
builder.add_node("prompt_enhance", prompt_enhance_node, metadata={"type": "agent", "llm_cfg": "config/prompt_enhance_cfg.json"})

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
        "保存历史": "save",
        "任务管理": "task_route",
        "工具中心": "tool_route"
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
        "用户注册": "register_with_limit",
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

# 各业务分支汇聚到统一返回节点
builder.add_edge("check_rate_limit", "format_response")
builder.add_edge("update_rate_limit", "format_response")
builder.add_edge("register_with_limit", "format_response")
builder.add_edge("get_user", "format_response")
builder.add_edge("get_user_by_id", "format_response")
builder.add_edge("update_user", "format_response")
builder.add_edge("delete_user", "format_response")
builder.add_edge("list_users", "format_response")
builder.add_edge("upload", "format_response")
builder.add_edge("save", "format_response")
builder.add_edge("create_task", "format_response")
builder.add_edge("update_task", "format_response")
builder.add_edge("delete_task", "format_response")
builder.add_edge("list_tasks", "format_response")
builder.add_edge("reverse_image", "format_response")
builder.add_edge("translate_doubao", "format_response")
builder.add_edge("prompt_enhance", "format_response")

# 统一返回节点到结束
builder.add_edge("format_response", END)

# 编译图
main_graph = builder.compile()
