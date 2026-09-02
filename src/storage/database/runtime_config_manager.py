"""运行时配置管理接口"""
import time
import uuid
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from storage.database.shared.model import RuntimeConfigs


class RuntimeConfigCreate(BaseModel):
    config_key: str = Field(..., description="配置唯一键")
    config_scope: str = Field(..., description="配置作用域")
    config_type: str = Field(..., description="配置类型")
    content_json: dict = Field(..., description="配置内容 JSON")
    is_active: bool = Field(default=True, description="是否启用")
    is_public: bool = Field(default=False, description="是否允许公开读取")
    updated_by: str = Field(..., description="更新人用户ID")


class RuntimeConfigManager:
    @staticmethod
    def _to_dict(config: RuntimeConfigs) -> dict:
        return {
            "id": config.id,
            "config_key": config.config_key,
            "config_scope": config.config_scope,
            "config_type": config.config_type,
            "content_json": config.content_json,
            "is_active": config.is_active,
            "is_public": config.is_public,
            "updated_by": config.updated_by,
            "created_at": config.created_at,
            "updated_at": config.updated_at,
        }

    @staticmethod
    def get_public_config(db: Session, config_key: str) -> tuple[bool, Optional[dict], Optional[str]]:
        try:
            config = db.query(RuntimeConfigs).filter(
                RuntimeConfigs.config_key == config_key,
                RuntimeConfigs.is_active == True,
                RuntimeConfigs.is_public == True,
            ).first()
            if not config:
                return False, None, "配置不存在或未公开"
            return True, RuntimeConfigManager._to_dict(config), None
        except Exception as e:
            return False, None, f"查询公开运行时配置失败: {str(e)}"

    @staticmethod
    def get_config_by_key(db: Session, config_key: str) -> tuple[bool, Optional[dict], Optional[str]]:
        try:
            config = db.query(RuntimeConfigs).filter(RuntimeConfigs.config_key == config_key).first()
            if not config:
                return False, None, "配置不存在"
            return True, RuntimeConfigManager._to_dict(config), None
        except Exception as e:
            return False, None, f"查询运行时配置失败: {str(e)}"

    @staticmethod
    def upsert_config(db: Session, config_data: RuntimeConfigCreate) -> tuple[bool, Optional[dict], Optional[str]]:
        try:
            now = int(time.time() * 1000)
            config = db.query(RuntimeConfigs).filter(RuntimeConfigs.config_key == config_data.config_key).first()

            if config:
                config.config_scope = config_data.config_scope
                config.config_type = config_data.config_type
                config.content_json = config_data.content_json
                config.is_active = config_data.is_active
                config.is_public = config_data.is_public
                config.updated_by = config_data.updated_by
                config.updated_at = now
            else:
                config = RuntimeConfigs(
                    id=f"rtc_{uuid.uuid4().hex[:28]}",
                    config_key=config_data.config_key,
                    config_scope=config_data.config_scope,
                    config_type=config_data.config_type,
                    content_json=config_data.content_json,
                    is_active=config_data.is_active,
                    is_public=config_data.is_public,
                    updated_by=config_data.updated_by,
                    created_at=now,
                    updated_at=now,
                )
                db.add(config)

            db.commit()
            db.refresh(config)
            return True, RuntimeConfigManager._to_dict(config), None
        except Exception as e:
            db.rollback()
            return False, None, f"保存运行时配置失败: {str(e)}"
