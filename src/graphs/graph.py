from langgraph.graph import StateGraph, END
from graphs.state import (
    GlobalState,
    GraphInput,
    GraphOutput,
    RegisterLoginInput,
    UploadInput,
    SaveInput,
    HistoryInput,
    FormatResponseInput
)
from graphs.node import (
    register_login_node,
    upload_node,
    save_node,
    history_node,
    format_response_node
)


def route_by_call_type(state: GlobalState) -> str:
    """
    title: 根据调用类型路由
    desc: 根据 call_type 参数将请求路由到不同的处理节点
    """
    call_type = state.call_type

    if call_type in ["register", "login"]:
        return "注册/登录"
    elif call_type == "upload":
        return "文件上传"
    elif call_type == "save":
        return "保存历史"
    elif call_type == "history":
        return "历史查询"
    else:
        return "未知类型"


# 创建状态图，指定图的入参和出参
builder = StateGraph(GlobalState, input_schema=GraphInput, output_schema=GraphOutput)

# 添加节点
builder.add_node("register_login", register_login_node)
builder.add_node("upload", upload_node)
builder.add_node("save", save_node)
builder.add_node("history", history_node)
builder.add_node("format_response", format_response_node)

# 设置入口点
builder.set_entry_point("router")

# 添加路由节点（虚拟节点，用于条件分支）
builder.add_node("router", lambda state: state)

# 添加条件分支
builder.add_conditional_edges(
    source="router",
    path=route_by_call_type,
    path_map={
        "注册/登录": "register_login",
        "文件上传": "upload",
        "保存历史": "save",
        "历史查询": "history",
        "未知类型": "format_response"
    }
)

# 各业务分支汇聚到统一返回节点
builder.add_edge("register_login", "format_response")
builder.add_edge("upload", "format_response")
builder.add_edge("save", "format_response")
builder.add_edge("history", "format_response")

# 统一返回节点到结束
builder.add_edge("format_response", END)

# 编译图
main_graph = builder.compile()
