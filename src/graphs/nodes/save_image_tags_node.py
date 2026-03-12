from typing import Optional
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from graphs.state import SaveImageTagsInput, SaveImageTagsOutput
from storage.database.task_manager import TaskManager
from storage.database.db import get_session


def save_image_tags_node(state: SaveImageTagsInput, config: RunnableConfig, runtime: Runtime[Context]) -> SaveImageTagsOutput:
    """
    title: 保存图像标签
    desc: 将生成的场景标签和产品标签保存到任务记录中
    integrations: 数据库
    """
    ctx = runtime.context

    if not state.task_id:
        return SaveImageTagsOutput(
            success=False,
            error="缺少任务ID"
        )

    try:
        db = get_session()
        try:
            task_mgr = TaskManager()
            
            # 查询任务
            db_task = task_mgr.get_task_by_id(db, state.task_id)
            
            if not db_task:
                return SaveImageTagsOutput(
                    success=False,
                    error="任务不存在"
                )
            
            # 保存标签
            db_task.scene_tags = state.scene_tags
            db_task.product_tags = state.product_tags
            
            db.add(db_task)
            db.commit()
            db.refresh(db_task)
            
            return SaveImageTagsOutput(
                success=True,
                scene_tags=db_task.scene_tags,
                product_tags=db_task.product_tags
            )
            
        finally:
            db.close()
            
    except Exception as e:
        import logging
        logging.error(f"保存标签失败: {e}", exc_info=True)
        return SaveImageTagsOutput(
            success=False,
            error=str(e)
        )
