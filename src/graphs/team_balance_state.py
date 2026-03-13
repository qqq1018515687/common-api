"""
团队余额状态定义 - 完全重写
"""
from pydantic import BaseModel, Field
from typing import Optional


# ============ 团队管理节点（合并所有管理操作）============
class TeamManageInput(BaseModel):
    """团队管理节点输入"""
    action: str = Field(..., description="操作类型")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    username: Optional[str] = Field(default=None, description="用户名")
    name: Optional[str] = Field(default=None, description="团队名称")
    amount: Optional[int] = Field(default=None, description="金额")
    days: Optional[int] = Field(default=30, description="查询天数")
    target_user_id: Optional[str] = Field(default=None, description="目标用户ID")
    target_username: Optional[str] = Field(default=None, description="目标用户名")
    target_role: Optional[str] = Field(default=None, description="目标角色")
    description: Optional[str] = Field(default=None, description="描述")
    original_record_id: Optional[str] = Field(default=None, description="原消费记录ID")
    reason: Optional[str] = Field(default=None, description="退款原因")


class TeamManageOutput(BaseModel):
    """团队管理节点输出"""
    response_data: dict = Field(default={}, description="响应数据")
