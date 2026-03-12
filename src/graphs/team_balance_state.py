from pydantic import BaseModel, Field
from typing import Optional


class InitTeamBalanceInput(BaseModel):
    """初始化团队余额系统的输入"""
    action: str = Field(..., description="操作类型：init/check")


class InitTeamBalanceOutput(BaseModel):
    """初始化团队余额系统的输出"""
    result: dict = Field(..., description="操作结果")
