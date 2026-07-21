import logging
from typing import Optional

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from storage.database import recharge_code_manager


logger = logging.getLogger(__name__)


class RechargeCodeInput(BaseModel):
    operation_type: Optional[str] = Field(default=None, description="兑换码操作")
    user_id: Optional[str] = Field(default=None, description="当前用户ID")
    operator_role: Optional[str] = Field(default=None, description="操作者角色")
    operator_user_id: Optional[str] = Field(default=None, description="管理员ID")
    batch_id: Optional[str] = Field(default=None, description="批次ID")
    code_id: Optional[str] = Field(default=None, description="兑换码ID")
    recharge_code: Optional[str] = Field(default=None, description="用户输入的兑换码")
    name: Optional[str] = Field(default=None, description="批次名称")
    credit_type: Optional[str] = Field(default=None, description="personal_gold/team_gold")
    target_credit_type: Optional[str] = Field(default=None, description="兑换到账类型 personal_gold/team_gold")
    amount: Optional[float] = Field(default=None, description="充值金额")
    limit: Optional[int] = Field(default=None, description="返回数量")
    status: Optional[str] = Field(default=None, description="状态筛选")
    channel: Optional[str] = Field(default=None, description="渠道")
    note: Optional[str] = Field(default=None, description="备注")
    expires_at: Optional[object] = Field(default=None, description="过期时间")
    search: Optional[str] = Field(default=None, description="搜索词")
    team_id: Optional[str] = Field(default=None, description="团队ID筛选")


class RechargeCodeOutput(BaseModel):
    response_data: dict = Field(default={}, description="统一响应数据")


def _success(data: object, msg: str = "操作成功") -> RechargeCodeOutput:
    return RechargeCodeOutput(response_data={"code": 0, "msg": msg, "data": data})


def _failure(message: str, code: int = 400) -> RechargeCodeOutput:
    return RechargeCodeOutput(response_data={"code": code, "msg": message, "data": None})


def _is_admin(state: RechargeCodeInput) -> bool:
    return (state.operator_role or "").strip().lower() in {"admin", "administrator", "管理员"}


def recharge_code_node(state: RechargeCodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> RechargeCodeOutput:
    """兑换码管理与兑换节点。"""
    operation_type = state.operation_type or "redeem"
    try:
        if operation_type == "redeem":
            if not state.user_id:
                return _failure("用户未登录", 401)
            if not state.recharge_code:
                return _failure("兑换码不能为空")
            return _success(recharge_code_manager.redeem(
                raw_code=state.recharge_code,
                user_id=state.user_id,
                target_credit_type=state.target_credit_type,
            ), "兑换成功")

        if operation_type == "list_redemptions":
            if not _is_admin(state) and not state.user_id:
                return _failure("用户未登录", 401)
            query_user_id = state.user_id if not _is_admin(state) else state.user_id
            return _success(recharge_code_manager.list_redemptions(
                user_id=query_user_id,
                team_id=state.team_id,
                limit=state.limit or 100,
            ))

        if not _is_admin(state):
            return _failure("无权操作兑换码", 403)

        operator_user_id = state.operator_user_id or state.user_id
        if operation_type == "create_batch":
            if not operator_user_id:
                return _failure("管理员ID不能为空")
            return _success(recharge_code_manager.create_batch(
                name=state.name or "金豆兑换码",
                credit_type=state.credit_type or "gold",
                amount=state.amount,
                code_count=state.limit or 1,
                created_by=operator_user_id,
                channel=state.channel,
                expires_at=state.expires_at,
                note=state.note,
            ), "批次生成成功")

        if operation_type == "list_batches":
            return _success(recharge_code_manager.list_batches(status=state.status, limit=state.limit or 100))

        if operation_type == "list_codes":
            return _success(recharge_code_manager.list_codes(
                batch_id=state.batch_id,
                status=state.status,
                search=state.search,
                user_id=state.user_id,
                limit=state.limit or 200,
            ))

        if operation_type == "disable_code":
            if not state.code_id:
                return _failure("兑换码ID不能为空")
            return _success(recharge_code_manager.disable_code(code_id=state.code_id), "兑换码已禁用")

        if operation_type == "disable_batch":
            if not state.batch_id:
                return _failure("批次ID不能为空")
            return _success(recharge_code_manager.disable_batch(batch_id=state.batch_id), "批次已禁用")

        return _failure(f"不支持的兑换码操作: {operation_type}")
    except Exception as exc:
        logger.exception("兑换码操作失败")
        return _failure(str(exc), 500)
