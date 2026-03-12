from typing import Optional
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from graphs.state import CheckNeedTagsInput, CheckNeedTagsOutput


def check_need_tags_node(state: CheckNeedTagsInput, config: RunnableConfig, runtime: Runtime[Context]) -> CheckNeedTagsOutput:
    """
    title: 检查是否需要生成标签
    desc: 检查任务状态和结果，判断是否需要生成图像标签
    integrations: 
    """
    ctx = runtime.context

    # 判断是否需要生成标签：任务状态为 completed 且有图像URL
    need_tags = (
        state.status == 'completed' and 
        state.task_result and 
        state.task_result.get('url')
    )

    # 提取图像URL
    image_url = None
    if need_tags and state.task_result:
        image_url = state.task_result.get('url')

    return CheckNeedTagsOutput(
        task_id=state.task_id,
        status=state.status,
        task_result=state.task_result,
        need_tags=need_tags,
        image_url=image_url
    )
