from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy import and_, or_

from storage.database.db import get_session
from storage.database.shared.model import TagPoolVersions, TagChangeHistory


class TagPoolManager:
    """标签池管理器"""
    
    @staticmethod
    def get_active_version(pool_type: str) -> Optional[int]:
        """获取激活的标签池版本
        
        Args:
            pool_type: scene / product
        
        Returns:
            激活的版本号，如果没有则返回 None
        """
        db = get_session()
        try:
            version_record = db.query(TagPoolVersions).filter(
                TagPoolVersions.pool_type == pool_type,
                TagPoolVersions.is_active == True
            ).first()
            
            return version_record.version if version_record else None
        finally:
            db.close()
    
    @staticmethod
    def get_tags(pool_type: str, version: Optional[int] = None) -> Dict:
        """获取标签池
        
        Args:
            pool_type: scene / product
            version: 版本号，None 表示获取最新激活版本
        
        Returns:
            标签池数据：{"version": 1, "tags": [{"name": "...", "desc": "..."}]}
        """
        db = get_session()
        try:
            if version is None:
                version = TagPoolManager.get_active_version(pool_type)
                if version is None:
                    # 如果没有激活版本，返回默认版本1
                    version = 1
            
            pool_record = db.query(TagPoolVersions).filter(
                TagPoolVersions.pool_type == pool_type,
                TagPoolVersions.version == version
            ).first()
            
            if not pool_record:
                return {"version": version, "tags": []}
            
            return {
                "version": version,
                "tags": pool_record.tags if pool_record.tags else []
            }
        finally:
            db.close()
    
    @staticmethod
    def create_new_version(
        pool_type: str,
        tags: List[Dict],
        from_version: Optional[int] = None,
        created_by: Optional[str] = None
    ) -> Dict:
        """创建新的标签池版本
        
        Args:
            pool_type: scene / product
            tags: 新的标签列表
            from_version: 基于哪个版本创建
            created_by: 创建者ID
        
        Returns:
            新版本数据：{"version": 2, "tags": [...]}
        """
        db = get_session()
        try:
            # 获取当前最新版本
            if from_version is None:
                latest = db.query(TagPoolVersions).filter(
                    TagPoolVersions.pool_type == pool_type
                ).order_by(TagPoolVersions.version.desc()).first()
                from_version = latest.version if latest else 0
            
            # 创建新版本
            new_version = from_version + 1
            
            new_pool = TagPoolVersions(
                pool_type=pool_type,
                version=new_version,
                tags=tags,
                is_active=False,  # 默认不激活，需要手动激活
                created_by=created_by
            )
            
            db.add(new_pool)
            db.commit()
            db.refresh(new_pool)
            
            return {
                "version": new_version,
                "tags": tags
            }
        finally:
            db.close()
    
    @staticmethod
    def activate_version(pool_type: str, version: int, activated_by: Optional[str] = None) -> bool:
        """激活指定版本的标签池
        
        Args:
            pool_type: scene / product
            version: 版本号
            activated_by: 激活者ID
        
        Returns:
            是否激活成功
        """
        db = get_session()
        try:
            # 检查目标版本是否存在
            pool_record = db.query(TagPoolVersions).filter(
                TagPoolVersions.pool_type == pool_type,
                TagPoolVersions.version == version
            ).first()
            
            if not pool_record:
                return False
            
            # 获取当前激活版本
            current_version = TagPoolManager.get_active_version(pool_type)
            
            # 取消当前激活的版本
            db.query(TagPoolVersions).filter(
                TagPoolVersions.pool_type == pool_type,
                TagPoolVersions.is_active == True
            ).update({"is_active": False})
            
            # 激活新版本
            pool_record.is_active = True
            pool_record.activated_at = datetime.now()
            pool_record.activated_by = activated_by
            
            db.commit()
            
            # 记录变更历史
            history = TagChangeHistory(
                from_version=current_version,
                to_version=version,
                pool_type=pool_type,
                change_type="activate_version",
                tag_name=f"Version {version}",
                change_details={"tags": pool_record.tags},
                reason=f"激活版本 {version}",
                created_by=activated_by
            )
            db.add(history)
            db.commit()
            
            return True
        finally:
            db.close()
    
    @staticmethod
    def rollback_version(pool_type: str, target_version: int, activated_by: Optional[str] = None) -> bool:
        """回滚到指定版本
        
        Args:
            pool_type: scene / product
            target_version: 目标版本号
            activated_by: 操作者ID
        
        Returns:
            是否回滚成功
        """
        db = get_session()
        try:
            # 检查目标版本是否存在
            pool_record = db.query(TagPoolVersions).filter(
                TagPoolVersions.pool_type == pool_type,
                TagPoolVersions.version == target_version
            ).first()
            
            if not pool_record:
                return False
            
            # 获取当前激活版本
            current_version = TagPoolManager.get_active_version(pool_type)
            
            # 取消当前激活
            db.query(TagPoolVersions).filter(
                TagPoolVersions.pool_type == pool_type,
                TagPoolVersions.is_active == True
            ).update({"is_active": False})
            
            # 激活目标版本
            pool_record.is_active = True
            pool_record.activated_at = datetime.now()
            pool_record.activated_by = activated_by
            
            db.commit()
            
            # 记录回滚历史
            history = TagChangeHistory(
                from_version=current_version,
                to_version=target_version,
                pool_type=pool_type,
                change_type="rollback",
                tag_name=f"Rollback to Version {target_version}",
                change_details={"previous_version": current_version},
                reason=f"从版本 {current_version} 回滚到版本 {target_version}",
                created_by=activated_by
            )
            db.add(history)
            db.commit()
            
            return True
        finally:
            db.close()
    
    @staticmethod
    def get_version_history(pool_type: str) -> List[Dict]:
        """获取版本历史
        
        Args:
            pool_type: scene / product
        
        Returns:
            版本历史列表
        """
        db = get_session()
        try:
            versions = db.query(TagPoolVersions).filter(
                TagPoolVersions.pool_type == pool_type
            ).order_by(TagPoolVersions.version.desc()).all()
            
            return [
                {
                    "version": v.version,
                    "is_active": v.is_active,
                    "tags_count": len(v.tags) if v.tags else 0,
                    "created_by": v.created_by,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                    "activated_at": v.activated_at.isoformat() if v.activated_at else None,
                    "activated_by": v.activated_by
                }
                for v in versions
            ]
        finally:
            db.close()
    
    @staticmethod
    def get_change_history(pool_type: str, limit: int = 50) -> List[Dict]:
        """获取变更历史
        
        Args:
            pool_type: scene / product
            limit: 返回记录数限制
        
        Returns:
            变更历史列表
        """
        db = get_session()
        try:
            changes = db.query(TagChangeHistory).filter(
                TagChangeHistory.pool_type == pool_type
            ).order_by(TagChangeHistory.created_at.desc()).limit(limit).all()
            
            return [
                {
                    "id": c.id,
                    "from_version": c.from_version,
                    "to_version": c.to_version,
                    "change_type": c.change_type,
                    "tag_name": c.tag_name,
                    "reason": c.reason,
                    "created_by": c.created_by,
                    "created_at": c.created_at.isoformat() if c.created_at else None
                }
                for c in changes
            ]
        finally:
            db.close()
    
    @staticmethod
    def initialize_default_pool(pool_type: str, default_tags: List[Dict]) -> Dict:
        """初始化默认标签池（如果不存在）
        
        Args:
            pool_type: scene / product
            default_tags: 默认标签列表
        
        Returns:
            初始化结果
        """
        db = get_session()
        try:
            # 检查是否已存在版本
            existing = db.query(TagPoolVersions).filter(
                TagPoolVersions.pool_type == pool_type
            ).first()
            
            if existing:
                return {
                    "success": False,
                    "message": f"{pool_type} 标签池已存在，跳过初始化",
                    "current_version": existing.version
                }
            
            # 创建版本1
            pool_record = TagPoolVersions(
                pool_type=pool_type,
                version=1,
                tags=default_tags,
                is_active=True,
                created_by="system",
                activated_at=datetime.now(),
                activated_by="system"
            )
            
            db.add(pool_record)
            db.commit()
            
            return {
                "success": True,
                "message": f"{pool_type} 标签池初始化成功",
                "version": 1
            }
        finally:
            db.close()
