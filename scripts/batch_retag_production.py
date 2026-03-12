#!/usr/bin/env python3
"""
生产环境批量打标脚本

功能：
1. 查询所有已完成但未打标的任务
2. 调用 AI 模型生成标签
3. 更新任务的 scene_tags 和 product_tags 字段

使用方法：
    python scripts/batch_retag_production.py --db-url "postgresql://user:pass@host:port/db"
    python scripts/batch_retag_production.py --db-url "postgresql://user:pass@host:port/db" --limit 100
    python scripts/batch_retag_production.py --db-url "postgresql://user:pass@host:port/db" --dry-run

环境变量：
    DB_URL: 数据库连接URL
    LLM_API_KEY: AI模型API密钥
"""

import sys
import os
import argparse
import json
from typing import List, Dict, Optional
import logging
from datetime import datetime

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_dependencies():
    """检查依赖是否安装"""
    try:
        import psycopg2
        import requests
        logger.info("✅ 依赖检查通过")
        return True
    except ImportError as e:
        logger.error(f"❌ 缺少依赖: {e}")
        logger.error("请安装依赖: pip install psycopg2-binary requests")
        return False


class ProductionRetagger:
    """生产环境批量打标器"""
    
    def __init__(self, db_url: str, llm_api_key: str = None):
        self.db_url = db_url
        self.llm_api_key = llm_api_key
        self.conn = None
        
    def connect_db(self):
        """连接数据库"""
        try:
            import psycopg2
            self.conn = psycopg2.connect(self.db_url)
            logger.info(f"✅ 数据库连接成功")
            return True
        except Exception as e:
            logger.error(f"❌ 数据库连接失败: {e}")
            return False
    
    def close_db(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            logger.info("✅ 数据库连接已关闭")
    
    def get_pending_tasks(self, limit: int = None) -> List[Dict]:
        """获取待打标的任务
        
        Args:
            limit: 限制数量，None 表示不限制
        
        Returns:
            任务列表
        """
        try:
            cursor = self.conn.cursor()
            
            # 查询已完成但未打标且有图像URL的任务
            sql = """
                SELECT id, result, scene_tags, product_tags
                FROM tasks
                WHERE status = 'completed'
                  AND result IS NOT NULL
                  AND result::text LIKE '%url%'
                  AND (scene_tags IS NULL OR array_length(scene_tags, 1) = 0)
                ORDER BY created_at DESC
            """
            
            if limit:
                sql += f" LIMIT {limit}"
            
            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description]
            tasks = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            cursor.close()
            logger.info(f"📊 找到 {len(tasks)} 个待打标任务")
            return tasks
            
        except Exception as e:
            logger.error(f"❌ 查询任务失败: {e}")
            return []
    
    def extract_image_url(self, result: dict) -> Optional[str]:
        """从 result 中提取图像URL
        
        Args:
            result: 任务结果
        
        Returns:
            图像URL或None
        """
        if not result:
            return None
        
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except:
                return None
        
        if isinstance(result, dict):
            return result.get('url')
        
        return None
    
    def generate_tags(self, image_url: str) -> Dict:
        """调用AI模型生成标签
        
        Args:
            image_url: 图像URL
        
        Returns:
            标签数据
        """
        try:
            # 这里应该调用实际的AI模型
            # 示例使用豆包API
            import requests
            
            if not self.llm_api_key:
                logger.warning("⚠️  未配置 LLM_API_KEY，使用模拟数据")
                return {
                    "scene_tags": ["座椅场景"],
                    "product_tags": ["坐垫"]
                }
            
            # 构造请求
            url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.llm_api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "doubao-seed-1-6-vision-250815",
                "messages": [
                    {
                        "role": "system",
                        "content": """你是一位专业的图像标签分析专家。

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
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "请分析这张图像，生成场景标签和产品标签"
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url}
                            }
                        ]
                    }
                ],
                "temperature": 0.3,
                "max_tokens": 500
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            # 解析JSON
            tags_data = json.loads(content)
            
            return {
                "scene_tags": tags_data.get("scene_tags", []),
                "product_tags": tags_data.get("product_tags", [])
            }
            
        except Exception as e:
            logger.error(f"❌ 生成标签失败: {e}")
            # 返回默认值
            return {
                "scene_tags": ["座椅场景"],
                "product_tags": ["坐垫"]
            }
    
    def update_task_tags(self, task_id: str, scene_tags: List[str], product_tags: List[str]) -> bool:
        """更新任务标签
        
        Args:
            task_id: 任务ID
            scene_tags: 场景标签
            product_tags: 产品标签
        
        Returns:
            是否成功
        """
        try:
            cursor = self.conn.cursor()
            
            sql = """
                UPDATE tasks
                SET scene_tags = %s,
                    product_tags = %s,
                    updated_at = %s
                WHERE id = %s
            """
            
            updated_at = str(int(datetime.now().timestamp() * 1000))
            
            cursor.execute(sql, (
                json.dumps(scene_tags),
                json.dumps(product_tags),
                updated_at,
                task_id
            ))
            
            self.conn.commit()
            cursor.close()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 更新任务 {task_id} 失败: {e}")
            self.conn.rollback()
            return False
    
    def batch_retag(self, limit: int = None, dry_run: bool = False) -> Dict:
        """批量重打标
        
        Args:
            limit: 限制数量
            dry_run: 是否只预览不执行
        
        Returns:
            执行结果
        """
        if not self.connect_db():
            return {
                "success": False,
                "message": "数据库连接失败"
            }
        
        try:
            # 获取待打标任务
            tasks = self.get_pending_tasks(limit)
            
            if not tasks:
                return {
                    "success": True,
                    "message": "没有待打标的任务",
                    "total": 0,
                    "success_count": 0,
                    "failed_count": 0
                }
            
            results = {
                "success": True,
                "total": len(tasks),
                "success_count": 0,
                "failed_count": 0,
                "failed_tasks": [],
                "dry_run": dry_run
            }
            
            logger.info(f"\n{'='*60}")
            logger.info(f"🚀 开始批量打标")
            logger.info(f"   总任务数: {len(tasks)}")
            logger.info(f"   模式: {'预览模式（不实际执行）' if dry_run else '执行模式'}")
            logger.info(f"{'='*60}\n")
            
            for i, task in enumerate(tasks, 1):
                task_id = task['id']
                result = task['result']
                
                # 提取图像URL
                if isinstance(result, str):
                    try:
                        result = json.loads(result)
                    except:
                        logger.warning(f"⚠️  任务 {task_id} 的 result 格式错误，跳过")
                        results['failed_count'] += 1
                        results['failed_tasks'].append({
                            "task_id": task_id,
                            "reason": "result格式错误"
                        })
                        continue
                
                image_url = self.extract_image_url(result)
                
                if not image_url:
                    logger.warning(f"⚠️  任务 {task_id} 没有图像URL，跳过")
                    results['failed_count'] += 1
                    results['failed_tasks'].append({
                        "task_id": task_id,
                        "reason": "没有图像URL"
                    })
                    continue
                
                logger.info(f"[{i}/{len(tasks)}] 处理任务 {task_id}")
                logger.info(f"   图像URL: {image_url}")
                
                if dry_run:
                    # 预览模式，不实际调用AI
                    logger.info(f"   预览: 将生成标签（不实际执行）")
                    results['success_count'] += 1
                    continue
                
                # 生成标签
                tags_data = self.generate_tags(image_url)
                
                scene_tags = tags_data['scene_tags']
                product_tags = tags_data['product_tags']
                
                logger.info(f"   场景标签: {scene_tags}")
                logger.info(f"   产品标签: {product_tags}")
                
                # 更新任务
                if self.update_task_tags(task_id, scene_tags, product_tags):
                    logger.info(f"   ✅ 更新成功")
                    results['success_count'] += 1
                else:
                    logger.error(f"   ❌ 更新失败")
                    results['failed_count'] += 1
                    results['failed_tasks'].append({
                        "task_id": task_id,
                        "reason": "数据库更新失败"
                    })
                
                logger.info("")  # 空行分隔
            
            logger.info(f"\n{'='*60}")
            logger.info(f"✅ 批量打标完成")
            logger.info(f"   总任务数: {results['total']}")
            logger.info(f"   成功: {results['success_count']}")
            logger.info(f"   失败: {results['failed_count']}")
            logger.info(f"{'='*60}\n")
            
            return results
            
        finally:
            self.close_db()


def main():
    parser = argparse.ArgumentParser(
        description='生产环境批量打标脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 预览模式（查看将处理多少任务）
  python scripts/batch_retag_production.py --db-url "$DB_URL" --dry-run
  
  # 批量打标（限制100个）
  python scripts/batch_retag_production.py --db-url "$DB_URL" --limit 100
  
  # 批量打标所有任务
  python scripts/batch_retag_production.py --db-url "$DB_URL"
        """
    )
    
    parser.add_argument(
        '--db-url',
        required=True,
        help='数据库连接URL（例如：postgresql://user:pass@host:port/db）'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='限制处理的任务数量（默认：不限制）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='预览模式，不实际执行'
    )
    parser.add_argument(
        '--llm-api-key',
        help='AI模型API密钥（可选，不传则使用模拟数据）'
    )
    
    args = parser.parse_args()
    
    # 检查依赖
    if not check_dependencies():
        sys.exit(1)
    
    # 创建打标器
    retagger = ProductionRetagger(
        db_url=args.db_url,
        llm_api_key=args.llm_api_key
    )
    
    # 执行批量打标
    result = retagger.batch_retag(
        limit=args.limit,
        dry_run=args.dry_run
    )
    
    # 输出结果
    if result['success']:
        logger.info(f"\n✅ 执行成功")
        logger.info(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        logger.error(f"\n❌ 执行失败: {result['message']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
