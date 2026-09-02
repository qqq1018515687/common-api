"""运行时配置处理节点"""
from typing import Optional

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from storage.database.db import get_session
from storage.database.runtime_config_manager import RuntimeConfigCreate, RuntimeConfigManager


class RuntimeConfigHandlerInput(BaseModel):
    operation_type: str = Field(..., description="操作类型：get_public_config/get_config_by_key/upsert_config")
    config_key: Optional[str] = Field(default=None, description="配置唯一键")
    config_scope: Optional[str] = Field(default=None, description="配置作用域")
    config_type: Optional[str] = Field(default=None, description="配置类型")
    content_json: Optional[dict] = Field(default=None, description="配置内容 JSON")
    is_public: Optional[bool] = Field(default=None, description="是否公开可读")
    is_active: Optional[bool] = Field(default=True, description="是否启用")
    operator_user_id: Optional[str] = Field(default=None, description="操作者用户ID")


class RuntimeConfigHandlerOutput(BaseModel):
    result: dict = Field(..., description="运行时配置操作结果")


def runtime_config_handler_node(
    state: RuntimeConfigHandlerInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> RuntimeConfigHandlerOutput:
    db = get_session()

    try:
        if state.operation_type == "get_public_config":
            if not state.config_key:
                return RuntimeConfigHandlerOutput(result={"code": 1, "msg": "缺少 config_key", "data": None})
            success, runtime_config, error = RuntimeConfigManager.get_public_config(db, state.config_key)
        elif state.operation_type == "get_config_by_key":
            if not state.config_key:
                return RuntimeConfigHandlerOutput(result={"code": 1, "msg": "缺少 config_key", "data": None})
            success, runtime_config, error = RuntimeConfigManager.get_config_by_key(db, state.config_key)
        elif state.operation_type == "upsert_config":
            if not state.config_key:
                return RuntimeConfigHandlerOutput(result={"code": 1, "msg": "缺少 config_key", "data": None})
            if not state.config_scope or not state.config_type or state.content_json is None:
                return RuntimeConfigHandlerOutput(result={"code": 1, "msg": "缺少配置内容", "data": None})

            success, runtime_config, error = RuntimeConfigManager.upsert_config(
                db,
                RuntimeConfigCreate(
                    config_key=state.config_key,
                    config_scope=state.config_scope,
                    config_type=state.config_type,
                    content_json=state.content_json,
                    is_active=state.is_active if state.is_active is not None else True,
                    is_public=state.is_public if state.is_public is not None else False,
                    updated_by=state.operator_user_id or "system",
                ),
            )
        else:
            return RuntimeConfigHandlerOutput(result={"code": 1, "msg": f"不支持的操作类型: {state.operation_type}", "data": None})

        if success:
            return RuntimeConfigHandlerOutput(result={"code": 0, "msg": "操作成功", "data": {"config": runtime_config}})

        return RuntimeConfigHandlerOutput(result={"code": 1, "msg": error or "操作失败", "data": None})
    finally:
        db.close()
