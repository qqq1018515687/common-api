"""
批量打标API接口
提供通过API触发批量打标的功能
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import logging
import json
import time
from datetime import datetime

# 导入项目相关模块
from storage.database.shared.model import Task, engine
from sqlalchemy.orm import Session
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/batch-retag", tags=["批量打标"])


def get_db():
    """获取数据库会话"""
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()


class BatchRetagRequest(BaseModel):
    """批量打标请求参数"""
    limit: Optional[int] = Field(None, description="限制处理的任务数量，默认不限制")
    dry_run: bool = Field(False, description="预览模式，只查询不实际更新")
    use_mock_data: bool = Field(False, description="使用模拟数据（不调用AI模型）")


class BatchRetagResponse(BaseModel):
    """批量打标响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="结果消息")
    total: int = Field(default=0, description="总任务数")
    success_count: int = Field(default=0, description="成功数量")
    failed_count: int = Field(default=0, description="失败数量")
    failed_tasks: List[Dict] = Field(default_factory=list, description="失败任务列表")
    dry_run: bool = Field(default=False, description="是否为预览模式")
    processing_time: Optional[float] = Field(None, description="处理耗时（秒）")


class PendingTaskInfo(BaseModel):
    """待打标任务信息"""
    task_id: str
    image_url: str
    created_at: Optional[str] = None


class PreviewResponse(BaseModel):
    """预览响应"""
    success: bool
    message: str
    total: int
    tasks: List[PendingTaskInfo]


def extract_image_url(result: Optional[str | dict]) -> Optional[str]:
    """从result中提取图像URL"""
    if not result:
        return None
    
    try:
        # 如果是字符串，先解析为dict
        if isinstance(result, str):
            result_dict = json.loads(result)
        else:
            result_dict = result
        
        # 提取url字段
        if isinstance(result_dict, dict):
            return result_dict.get('url')
        
        return None
    except Exception as e:
        logger.warning(f"解析result失败: {e}")
        return None


def generate_tags_with_ai(image_url: str, use_mock: bool = False) -> Dict[str, List[str]]:
    """使用AI模型生成标签"""
    if use_mock:
        logger.info("使用模拟数据生成标签")
        return {
            "scene_tags": ["座椅场景"],
            "product_tags": ["坐垫"]
        }
    
    try:
        # 导入LLM技能
        from coze_coding_utils.llm.llm import LLM
        from langchain_core.messages import HumanMessage
        
        # 初始化LLM
        llm = LLM(
            model="doubao-seed-1-6-vision-250815",
            temperature=0.3,
            max_tokens=500
        )
        
        # 构造提示词
        system_prompt = """你是一位专业的图像标签分析专家。

场景标签池：
- 座椅场景：坐姿、椅子、沙发
- 睡眠场景：床、卧室、睡眠
- 躺卧场景：躺椅、沙发、躺卧
- 驾驶场景：汽车内部、座椅
- 办公场景：办公室、办公桌
- 客厅场景：客厅、沙发
- 装饰场景：蜡烛、台灯、温馨氛围
- 户外场景：户外、风景

产品标签池：
- 腰靠：腰部支撑，适用于座椅场景
- 腿枕：腿部支撑，适用于躺卧场景
- 融蜡灯：氛围装饰，适用于装饰场景
- 脚垫：脚部支撑，适用于驾驶、办公场景
- 枕头：头部支撑，适用于睡眠、躺卧场景
- 坐垫：臀部支撑，适用于座椅场景

要求：返回纯JSON格式，不要添加任何解释。

输出格式：
{
  "scene_tags": ["标签1", "标签2"],
  "product_tags": ["标签1"]
}"""
        
        user_prompt = "请分析这张图像，生成场景标签和产品标签"
        
        # 构造消息（多模态）
        message = HumanMessage(content=[
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": image_url}}
        ])
        
        # 调用LLM
        response = llm.invoke(
            messages=[message],
            system_prompt=system_prompt
        )
        
        # 解析响应
        content = response.content.strip()
        tags_data = json.loads(content)
        
        return {
            "scene_tags": tags_data.get("scene_tags", []),
            "product_tags": tags_data.get("product_tags", [])
        }
        
    except Exception as e:
        logger.error(f"AI模型调用失败: {e}")
        # 返回默认值
        return {
            "scene_tags": ["座椅场景"],
            "product_tags": ["坐垫"]
        }


@router.get("/preview", response_model=PreviewResponse)
async def preview_pending_tasks(
    limit: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    预览待打标的任务
    
    参数:
        limit: 限制返回的任务数量
    
    返回:
        待打标任务列表
    """
    try:
        # 查询待打标任务
        query = select(Task).where(
            Task.status == "completed",
            Task.result.isnot(None),
            (Task.scene_tags.is_(None)) | (Task.scene_tags == []),
            (Task.product_tags.is_(None)) | (Task.product_tags == [])
        ).order_by(Task.created_at.desc())
        
        if limit:
            query = query.limit(limit)
        
        tasks = db.scalars(query).all()
        
        # 构建响应
        pending_tasks = []
        for task in tasks:
            image_url = extract_image_url(task.result)
            if image_url:
                pending_tasks.append(PendingTaskInfo(
                    task_id=task.id,
                    image_url=image_url,
                    created_at=task.created_at.isoformat() if task.created_at else None
                ))
        
        return PreviewResponse(
            success=True,
            message=f"找到 {len(pending_tasks)} 个待打标任务",
            total=len(pending_tasks),
            tasks=pending_tasks
        )
        
    except Exception as e:
        logger.error(f"预览失败: {e}")
        raise HTTPException(status_code=500, detail=f"预览失败: {str(e)}")


@router.post("/execute", response_model=BatchRetagResponse)
async def execute_batch_retag(
    request: BatchRetagRequest,
    db: Session = Depends(get_db)
):
    """
    执行批量打标
    
    参数:
        limit: 限制处理的任务数量
        dry_run: 预览模式
        use_mock_data: 使用模拟数据
    
    返回:
        批量打标结果
    """
    start_time = time.time()
    
    try:
        logger.info(f"开始批量打标: limit={request.limit}, dry_run={request.dry_run}, use_mock={request.use_mock_data}")
        
        # 查询待打标任务
        query = select(Task).where(
            Task.status == "completed",
            Task.result.isnot(None),
            (Task.scene_tags.is_(None)) | (Task.scene_tags == []),
            (Task.product_tags.is_(None)) | (Task.product_tags == [])
        ).order_by(Task.created_at.desc())
        
        if request.limit:
            query = query.limit(request.limit)
        
        tasks = db.scalars(query).all()
        
        if not tasks:
            return BatchRetagResponse(
                success=True,
                message="没有待打标的任务",
                total=0,
                success_count=0,
                failed_count=0,
                dry_run=request.dry_run,
                processing_time=time.time() - start_time
            )
        
        results = {
            "success": True,
            "message": "",
            "total": len(tasks),
            "success_count": 0,
            "failed_count": 0,
            "failed_tasks": [],
            "dry_run": request.dry_run
        }
        
        logger.info(f"找到 {len(tasks)} 个待打标任务")
        
        # 处理每个任务
        for i, task in enumerate(tasks, 1):
            task_id = task.id
            image_url = extract_image_url(task.result)
            
            if not image_url:
                logger.warning(f"任务 {task_id} 没有图像URL，跳过")
                results["failed_count"] += 1
                results["failed_tasks"].append({
                    "task_id": task_id,
                    "reason": "没有图像URL"
                })
                continue
            
            logger.info(f"[{i}/{len(tasks)}] 处理任务 {task_id}")
            
            if request.dry_run:
                logger.info(f"预览模式: 将生成标签（不实际执行）")
                results["success_count"] += 1
                continue
            
            # 生成标签
            tags_data = generate_tags_with_ai(image_url, request.use_mock_data)
            
            scene_tags = tags_data["scene_tags"]
            product_tags = tags_data["product_tags"]
            
            logger.info(f"场景标签: {scene_tags}")
            logger.info(f"产品标签: {product_tags}")
            
            # 更新任务
            try:
                task.scene_tags = scene_tags
                task.product_tags = product_tags
                task.updated_at = datetime.now()
                db.commit()
                
                logger.info(f"✅ 任务 {task_id} 更新成功")
                results["success_count"] += 1
                
            except Exception as e:
                logger.error(f"❌ 任务 {task_id} 更新失败: {e}")
                db.rollback()
                results["failed_count"] += 1
                results["failed_tasks"].append({
                    "task_id": task_id,
                    "reason": str(e)
                })
        
        # 构建响应
        processing_time = time.time() - start_time
        results["processing_time"] = processing_time
        
        if results["failed_count"] == 0:
            results["message"] = f"批量打标完成，成功 {results['success_count']} 个任务，耗时 {processing_time:.2f}秒"
        else:
            results["message"] = f"批量打标完成，成功 {results['success_count']} 个，失败 {results['failed_count']} 个，耗时 {processing_time:.2f}秒"
        
        logger.info(f"批量打标完成: {results['message']}")
        
        return BatchRetagResponse(**results)
        
    except Exception as e:
        logger.error(f"批量打标失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量打标失败: {str(e)}")
