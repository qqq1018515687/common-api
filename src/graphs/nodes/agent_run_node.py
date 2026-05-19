import logging
from typing import Optional

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from storage.database.agent_run_manager import (
    create_run,
    get_run,
    list_runs,
    update_run,
    update_step,
)

logger = logging.getLogger(__name__)


class AgentRunInput(BaseModel):
    """Agent Run persistence node input."""
    operation_type: Optional[str] = Field(default=None, description="create_run/get_run/list_runs/update_run/update_step")
    user_id: Optional[str] = Field(default=None, description="Owner user id")
    team_id: Optional[str] = Field(default=None, description="Team id")
    prompt: Optional[str] = Field(default=None, description="Original prompt")
    status: Optional[str] = Field(default=None, description="Run or step status")
    task_id: Optional[str] = Field(default=None, description="Generated task id")
    limit: Optional[int] = Field(default=None, description="List limit")
    metadata: Optional[dict] = Field(default=None, description="Generic metadata")
    assets: Optional[list[dict]] = Field(default=None, description="Input assets")
    agent_preferences: Optional[dict] = Field(default=None, description="Agent preferences")
    agent_run_id: Optional[str] = Field(default=None, description="Agent run id")
    agent_step_id: Optional[str] = Field(default=None, description="Agent step id")
    agent_plan_type: Optional[str] = Field(default=None, description="Agent plan type")
    agent_plan: Optional[dict] = Field(default=None, description="Agent plan payload")
    agent_steps: Optional[list[dict]] = Field(default=None, description="Agent plan steps")
    agent_run_updates: Optional[dict] = Field(default=None, description="Run updates")
    agent_step_updates: Optional[dict] = Field(default=None, description="Step updates")


class AgentRunOutput(BaseModel):
    """Agent Run persistence node output."""
    response_data: dict = Field(default={}, description="Unified response data")


def _success(data: dict, msg: str = "操作成功") -> AgentRunOutput:
    return AgentRunOutput(response_data={"code": 0, "msg": msg, "data": data})


def _failure(msg: str, code: int = 1, error_code: str = "AGENT_RUN_ERROR") -> AgentRunOutput:
    return AgentRunOutput(response_data={"code": code, "error_code": error_code, "msg": msg, "data": None})


def agent_run_node(
    state: AgentRunInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> AgentRunOutput:
    """
    title: Agent Run persistence
    desc: Stores Agent run/step state for cross-device recovery and task linkage.
    integrations: database
    """
    void_context = runtime.context
    void_context

    try:
        operation_type = state.operation_type or "get_run"

        if operation_type == "create_run":
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            run = create_run(
                user_id=state.user_id,
                run_id=state.agent_run_id,
                team_id=state.team_id,
                status=state.status,
                plan_type=state.agent_plan_type,
                prompt=state.prompt,
                plan=state.agent_plan,
                steps=state.agent_steps,
                assets=state.assets,
                preferences=state.agent_preferences,
                metadata=state.metadata,
            )
            return _success({"run": run}, "Agent Run 已创建")

        if operation_type == "get_run":
            if not state.agent_run_id:
                return _failure("agent_run_id 不能为空", error_code="RUN_ID_REQUIRED")
            run = get_run(state.agent_run_id, user_id=state.user_id)
            if not run:
                return _failure("Agent Run 不存在", code=404, error_code="RUN_NOT_FOUND")
            return _success({"run": run}, "Agent Run 已获取")

        if operation_type == "list_runs":
            runs = list_runs(
                user_id=state.user_id,
                team_id=state.team_id,
                status=state.status,
                limit=state.limit,
            )
            return _success(runs, "Agent Run 列表已获取")

        if operation_type == "update_run":
            if not state.agent_run_id:
                return _failure("agent_run_id 不能为空", error_code="RUN_ID_REQUIRED")
            updates = dict(state.agent_run_updates or {})
            if state.status is not None:
                updates["status"] = state.status
            if state.metadata is not None:
                updates["metadata"] = state.metadata
            run = update_run(state.agent_run_id, updates, user_id=state.user_id)
            if not run:
                return _failure("Agent Run 不存在", code=404, error_code="RUN_NOT_FOUND")
            return _success({"run": run}, "Agent Run 已更新")

        if operation_type == "update_step":
            if not state.agent_run_id or not state.agent_step_id:
                return _failure("agent_run_id 和 agent_step_id 不能为空", error_code="STEP_ID_REQUIRED")
            updates = dict(state.agent_step_updates or {})
            if state.status is not None:
                updates["status"] = state.status
            if state.task_id is not None:
                updates["task_id"] = state.task_id
            if state.metadata is not None:
                updates["metadata"] = state.metadata
            run = update_step(
                run_id=state.agent_run_id,
                step_id=state.agent_step_id,
                updates=updates,
                user_id=state.user_id,
            )
            if not run:
                return _failure("Agent Run 或 Step 不存在", code=404, error_code="STEP_NOT_FOUND")
            return _success({"run": run}, "Agent Step 已更新")

        return _failure(f"不支持的 Agent Run 操作: {operation_type}", code=400, error_code="UNSUPPORTED_OPERATION")

    except Exception as exc:
        logger.error(f"Agent Run 操作失败: {exc}")
        return _failure(f"Agent Run 操作失败: {str(exc)}", code=500, error_code="INTERNAL_ERROR")
