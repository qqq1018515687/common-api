"""
团队余额状态定义
所有团队余额相关节点共享这些输入输出类型
"""
from pydantic import BaseModel, Field
from typing import Optional


# ============ 团队路由节点（透传所有必要字段）============
class TeamRouteInput(BaseModel):
    """团队余额路由输入"""
    action: Optional[str] = Field(default=None, description="操作类型")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    username: Optional[str] = Field(default=None, description="用户名")
    name: Optional[str] = Field(default=None, description="团队名称")
    amount: Optional[int] = Field(default=None, description="金额")
    description: Optional[str] = Field(default=None, description="描述")
    days: Optional[int] = Field(default=None, description="查询天数")
    target_user_id: Optional[str] = Field(default=None, description="目标用户ID")
    target_username: Optional[str] = Field(default=None, description="目标用户名")
    target_role: Optional[str] = Field(default=None, description="目标角色")
    original_record_id: Optional[str] = Field(default=None, description="原消费记录ID")
    reason: Optional[str] = Field(default=None, description="退款原因")
    task_id: Optional[str] = Field(default=None, description="关联任务ID")
    operator_user_id: Optional[str] = Field(default=None, description="操作者用户ID")


class TeamRouteOutput(BaseModel):
    """团队余额路由输出（透传所有字段）"""
    action: Optional[str] = Field(default=None, description="操作类型")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    username: Optional[str] = Field(default=None, description="用户名")
    name: Optional[str] = Field(default=None, description="团队名称")
    amount: Optional[int] = Field(default=None, description="金额")
    description: Optional[str] = Field(default=None, description="描述")
    days: Optional[int] = Field(default=None, description="查询天数")
    target_user_id: Optional[str] = Field(default=None, description="目标用户ID")
    target_username: Optional[str] = Field(default=None, description="目标用户名")
    target_role: Optional[str] = Field(default=None, description="目标角色")
    original_record_id: Optional[str] = Field(default=None, description="原消费记录ID")
    reason: Optional[str] = Field(default=None, description="退款原因")
    task_id: Optional[str] = Field(default=None, description="关联任务ID")
    operator_user_id: Optional[str] = Field(default=None, description="操作者用户ID")


# ============ 团队初始化节点 ============
class TeamInitInput(BaseModel):
    """团队初始化节点的输入"""
    action: Optional[str] = Field(default=None, description="操作类型：init/check")


class TeamInitOutput(BaseModel):
    """团队初始化节点的输出"""
    response_data: Optional[dict] = Field(default=None, description="响应数据")


# ============ 团队管理节点 ============
class TeamManageInput(BaseModel):
    """团队管理节点的输入"""
    action: Optional[str] = Field(default=None, description="操作类型：create_team/get_team/add_member/list_members")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    user_id: Optional[str] = Field(default=None, description="操作用户ID")
    username: Optional[str] = Field(default=None, description="操作用户名")
    name: Optional[str] = Field(default=None, description="团队名称")
    target_user_id: Optional[str] = Field(default=None, description="目标用户ID")
    target_username: Optional[str] = Field(default=None, description="目标用户名")
    target_role: Optional[str] = Field(default=None, description="目标角色：admin/member")


class TeamManageOutput(BaseModel):
    """团队管理节点的输出"""
    response_data: Optional[dict] = Field(default=None, description="响应数据")


# ============ 团队充值节点 ============
class TeamRechargeInput(BaseModel):
    """团队充值节点的输入"""
    action: Optional[str] = Field(default=None, description="操作类型：recharge")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    user_id: Optional[str] = Field(default=None, description="操作用户ID")
    username: Optional[str] = Field(default=None, description="操作用户名")
    operator_user_id: Optional[str] = Field(default=None, description="操作者用户ID")
    amount: Optional[int] = Field(default=None, description="充值金额")
    description: Optional[str] = Field(default=None, description="充值描述")


class TeamRechargeOutput(BaseModel):
    """团队充值节点的输出"""
    response_data: Optional[dict] = Field(default=None, description="响应数据")


# ============ 团队扣费节点 ============
class TeamDeductInput(BaseModel):
    """团队扣费节点的输入"""
    action: Optional[str] = Field(default=None, description="操作类型：deduct")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    username: Optional[str] = Field(default=None, description="用户名")
    amount: Optional[int] = Field(default=None, description="扣费金额")
    task_id: Optional[str] = Field(default=None, description="关联任务ID")
    description: Optional[str] = Field(default=None, description="扣费描述")


class TeamDeductOutput(BaseModel):
    """团队扣费节点的输出"""
    response_data: Optional[dict] = Field(default=None, description="响应数据")


# ============ 团队退款节点 ============
class TeamRefundInput(BaseModel):
    """团队退款节点的输入"""
    action: Optional[str] = Field(default=None, description="操作类型：refund")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    username: Optional[str] = Field(default=None, description="用户名")
    original_record_id: Optional[str] = Field(default=None, description="原消费记录ID")
    amount: Optional[int] = Field(default=None, description="退款金额")
    reason: Optional[str] = Field(default=None, description="退款原因")


class TeamRefundOutput(BaseModel):
    """团队退款节点的输出"""
    response_data: Optional[dict] = Field(default=None, description="响应数据")


# ============ 团队消费记录节点 ============
class TeamRecordsInput(BaseModel):
    """团队消费记录节点的输入"""
    action: Optional[str] = Field(default=None, description="操作类型：get_records/get_stats/get_member_stats")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    user_id: Optional[str] = Field(default=None, description="用户ID（可选，筛选特定用户的记录）")
    days: Optional[int] = Field(default=30, description="查询天数（默认30天）")
    limit: Optional[int] = Field(default=50, description="返回记录数限制")


class TeamRecordsOutput(BaseModel):
    """团队消费记录节点的输出"""
    response_data: Optional[dict] = Field(default=None, description="响应数据")
