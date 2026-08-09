import logging
from typing import Optional

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from storage.database import recharge_code_manager, recharge_order_manager


logger = logging.getLogger(__name__)


class RechargeCodeInput(BaseModel):
    operation_type: Optional[str] = Field(default=None, description="兑换码操作")
    user_id: Optional[str] = Field(default=None, description="当前用户ID")
    operator_role: Optional[str] = Field(default=None, description="操作者角色")
    operator_user_id: Optional[str] = Field(default=None, description="管理员ID")
    operator_id: Optional[str] = Field(default=None, description="人工介入者ID")
    ip: Optional[str] = Field(default=None, description="用户请求IP（兑换失败风控审计用）")
    batch_id: Optional[str] = Field(default=None, description="批次ID")
    code_id: Optional[str] = Field(default=None, description="兑换码ID")
    order_id: Optional[str] = Field(default=None, description="充值订单ID")
    order_no: Optional[str] = Field(default=None, description="充值订单号")
    recharge_code: Optional[str] = Field(default=None, description="用户输入的兑换码")
    name: Optional[str] = Field(default=None, description="批次名称")
    credit_type: Optional[str] = Field(default=None, description="personal_gold/team_gold")
    target_credit_type: Optional[str] = Field(default=None, description="兑换到账类型 personal_gold/team_gold")
    amount: Optional[float] = Field(default=None, description="充值金额")
    limit: Optional[int] = Field(default=None, description="返回数量")
    page: Optional[int] = Field(default=None, description="页码")
    status: Optional[str] = Field(default=None, description="状态筛选")
    channel: Optional[str] = Field(default=None, description="渠道")
    source_type: Optional[str] = Field(default=None, description="订单来源类型 paid/manual/compensation/campaign")
    package_id: Optional[str] = Field(default=None, description="套餐ID")
    package_name: Optional[str] = Field(default=None, description="套餐名称")
    external_order_id: Optional[str] = Field(default=None, description="外部支付订单号")
    external_ref: Optional[str] = Field(default=None, description="外部参考信息")
    start_time: Optional[object] = Field(default=None, description="起始时间（毫秒时间戳或 YYYY-MM-DD，按上海日期过滤）")
    end_time: Optional[object] = Field(default=None, description="结束时间（毫秒时间戳或 YYYY-MM-DD，按上海日期过滤）")
    reason: Optional[str] = Field(default=None, description="退款/取消原因")
    note: Optional[str] = Field(default=None, description="备注")
    expires_at: Optional[object] = Field(default=None, description="过期时间")
    search: Optional[str] = Field(default=None, description="搜索词")
    team_id: Optional[str] = Field(default=None, description="团队ID筛选")
    action: Optional[str] = Field(default=None, description="冲正处理动作 approve/reject/complete")
    resolution_note: Optional[str] = Field(default=None, description="冲正处理备注")
    reversal_status: Optional[str] = Field(default=None, description="冲正状态筛选 pending/approved/rejected/completed")


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
                ip=state.ip,
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

        operator_user_id = state.operator_id or state.operator_user_id or state.user_id
        if operation_type == "create_order":
            if not operator_user_id:
                return _failure("管理员ID不能为空")
            return _success(recharge_order_manager.create_order(
                user_id=state.user_id,
                team_id=state.team_id,
                package_id=state.package_id,
                package_name=state.package_name,
                amount_paid=state.amount,
                channel=state.channel or "manual",
                source_type=state.source_type or "paid",
                external_order_id=state.external_order_id,
                external_ref=state.external_ref,
                operator_id=operator_user_id,
                note=state.note,
            ), "订单创建成功")

        if operation_type == "list_orders":
            return _success(recharge_order_manager.list_orders(
                status=state.status,
                channel=state.channel,
                source_type=state.source_type,
                reversal_status=state.reversal_status,
                user_id=state.user_id,
                search=state.search,
                start_time=state.start_time,
                end_time=state.end_time,
                page=state.page or 1,
                limit=state.limit or 50,
            ))

        if operation_type == "get_order":
            if not state.order_id and not state.order_no:
                return _failure("订单ID或订单号不能为空")
            if state.order_id:
                return _success(recharge_order_manager.get_order(state.order_id))
            return _success(recharge_order_manager.get_order_by_no(state.order_no))

        if operation_type == "order_summary":
            return _success(recharge_order_manager.list_order_summary())

        if operation_type == "refund_order":
            if not state.order_id:
                return _failure("订单ID不能为空")
            return _success(recharge_order_manager.refund_order(
                order_id=state.order_id,
                operator_id=operator_user_id,
                reason=state.reason,
                amount=state.amount,
            ), "订单退款成功")

        if operation_type == "cancel_order":
            if not state.order_id:
                return _failure("订单ID不能为空")
            return _success(recharge_order_manager.cancel_order(
                order_id=state.order_id,
                operator_id=operator_user_id,
                reason=state.reason,
            ), "订单取消成功")

        if operation_type == "create_reversal_request":
            if not state.order_id:
                return _failure("订单ID不能为空")
            return _success(recharge_order_manager.create_reversal_request(
                order_id=state.order_id,
                requested_by=operator_user_id,
                reason=state.reason or "订单冲正申请"
            ), "冲正申请已提交")

        if operation_type == "review_reversal_request":
            if not state.order_id:
                return _failure("订单ID不能为空")
            return _success(recharge_order_manager.review_reversal_request(
                order_id=state.order_id,
                action=state.action or "",
                resolved_by=operator_user_id,
                resolution_note=state.resolution_note,
            ), "冲正申请处理成功")

        if operation_type == "complete_reversal_request":
            if not state.order_id:
                return _failure("订单ID不能为空")
            return _success(recharge_order_manager.complete_reversal_request(
                order_id=state.order_id,
                resolved_by=operator_user_id,
                resolution_note=state.resolution_note,
            ), "冲正执行完成")

        if operation_type == "preview_reversal_request":
            if not state.order_id:
                return _failure("订单ID不能为空")
            return _success(recharge_order_manager.preview_reversal_request(
                order_id=state.order_id,
            ), "冲正预检成功")

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
                order_id=state.order_id,
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
