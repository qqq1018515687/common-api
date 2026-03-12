#!/usr/bin/env python3
"""
标签池分析脚本

功能：
1. 分析标签使用情况
2. 发现高频但未在标签池中的场景
3. 生成标签优化建议
4. 支持时间范围限制（默认30天）
5. 支持一键应用更新

使用方法：
    python scripts/analyze_tags_enhanced.py                # 分析近30天
    python scripts/analyze_tags_enhanced.py --days 7      # 分析近7天
    python scripts/analyze_tags_enhanced.py --all         # 分析所有历史数据
    python scripts/analyze_tags_enhanced.py --apply       # 自动应用更新
"""

import sys
import os
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import func, and_, or_
from storage.database.db import get_session
from storage.database.shared.model import Tasks
from storage.database.tag_pool_manager import TagPoolManager


def analyze_tags(
    days: int = 30,
    analyze_all: bool = False,
    min_task_count: int = 3,
    min_confidence: float = 0.7
) -> Tuple[Dict, List[Dict]]:
    """
    分析标签使用情况，发现潜在的新标签
    
    Args:
        days: 分析近N天的数据（默认30天）
        analyze_all: 是否分析所有历史数据
        min_task_count: 最少任务数阈值
        min_confidence: 最小置信度阈值
    
    Returns:
        (分析报告, 建议列表)
    """
    db = get_session()
    try:
        # 1. 构造时间范围条件
        time_filter = None
        if not analyze_all:
            cutoff_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
            time_filter = Tasks.created_at >= cutoff_time
        
        print(f"🔍 开始分析标签使用情况...")
        print(f"   时间范围: {'所有历史数据' if analyze_all else f'近 {days} 天'}")
        print(f"   最小任务数: {min_task_count}")
        print(f"   最小置信度: {min_confidence}")
        
        # 2. 获取当前标签池
        scene_pool = TagPoolManager.get_tags("scene")
        product_pool = TagPoolManager.get_tags("product")
        
        current_scene_tags = [tag['name'] for tag in scene_pool['tags']]
        current_product_tags = [tag['name'] for tag in product_pool['tags']]
        
        print(f"   当前场景标签数: {len(current_scene_tags)}")
        print(f"   当前产品标签数: {len(current_product_tags)}")
        
        # 3. 统计标签使用频率
        tag_stats_query = db.query(
            func.unnest(Tasks.scene_tags).label('tag'),
            func.count(Tasks.id).label('count')
        ).filter(
            Tasks.status == 'completed',
            Tasks.scene_tags != None
        )
        
        if time_filter is not None:
            tag_stats_query = tag_stats_query.filter(time_filter)
        
        tag_stats = tag_stats_query.group_by('tag').all()
        
        print(f"   发现 {len(tag_stats)} 个已使用的标签")
        
        # 4. 查询未充分标记的任务
        tasks_query = db.query(Tasks).filter(
            Tasks.status == 'completed',
            Tasks.result != None,
            func.jsonb_typeof(Tasks.result) == 'object',
            func.jsonb_exists(Tasks.result, 'url')
        )
        
        if time_filter is not None:
            tasks_query = tasks_query.filter(time_filter)
        
        tasks = tasks_query.limit(100).all()
        
        print(f"   分析 {len(tasks)} 个未充分标记的任务...")
        
        # 5. 使用关键词检测发现潜在新标签（简化版）
        potential_new_tags = {}
        
        # 定义关键词映射
        keyword_mapping = {
            '厨房': {'tag_name': '厨房场景', 'desc': '厨房环境，包含炉灶、橱柜、烹饪器具等'},
            '炉灶': {'tag_name': '厨房场景', 'desc': '厨房环境，包含炉灶、橱柜、烹饪器具等'},
            '橱柜': {'tag_name': '厨房场景', 'desc': '厨房环境，包含炉灶、橱柜、烹饪器具等'},
            '烹饪': {'tag_name': '厨房场景', 'desc': '厨房环境，包含炉灶、橱柜、烹饪器具等'},
            '浴室': {'tag_name': '浴室场景', 'desc': '浴室环境，包含洗手台、淋浴设备等'},
            '卫生间': {'tag_name': '浴室场景', 'desc': '浴室环境，包含洗手台、淋浴设备等'},
            '洗手台': {'tag_name': '浴室场景', 'desc': '浴室环境，包含洗手台、淋浴设备等'},
            '阳台': {'tag_name': '阳台场景', 'desc': '阳台或露台环境'},
            '露台': {'tag_name': '阳台场景', 'desc': '阳台或露台环境'},
            '走廊': {'tag_name': '走廊场景', 'desc': '走廊或玄关区域'},
            '玄关': {'tag_name': '走廊场景', 'desc': '走廊或玄关区域'},
            '餐厅': {'tag_name': '餐厅场景', 'desc': '餐厅环境，包含餐桌、餐椅等'},
            '餐桌': {'tag_name': '餐厅场景', 'desc': '餐厅环境，包含餐桌、餐椅等'},
            '书房': {'tag_name': '书房场景', 'desc': '书房环境，包含书桌、书架等'},
            '书桌': {'tag_name': '书房场景', 'desc': '书房环境，包含书桌、书架等'},
            '健身房': {'tag_name': '健身房场景', 'desc': '健身环境，包含健身器材等'},
            '健身': {'tag_name': '健身房场景', 'desc': '健身环境，包含健身器材等'},
            '瑜伽': {'tag_name': '健身房场景', 'desc': '健身环境，包含健身器材等'},
            '儿童房': {'tag_name': '儿童房场景', 'desc': '儿童房间环境'},
            '玩具': {'tag_name': '儿童房场景', 'desc': '儿童房间环境'},
        }
        
        for task in tasks:
            # 只分析标签数量 <= 2 的任务
            if not task.scene_tags or len(task.scene_tags) <= 2:
                # 检查任务结果中是否有描述信息
                task_desc = ""
                if task.result:
                    # 提取描述信息（如果有）
                    if 'description' in task.result:
                        task_desc = task.result['description']
                    elif 'prompt' in task.result:
                        task_desc = task.result['prompt']
                
                # 关键词匹配
                for keyword, tag_info in keyword_mapping.items():
                    if keyword in task_desc:
                        tag_name = tag_info['tag_name']
                        
                        # 检查是否已在标签池中
                        if tag_name not in current_scene_tags:
                            if tag_name not in potential_new_tags:
                                potential_new_tags[tag_name] = {
                                    'tag_name': tag_name,
                                    'task_count': 0,
                                    'task_ids': [],
                                    'descriptions': set(),
                                    'keywords_found': set()
                                }
                            
                            potential_new_tags[tag_name]['task_count'] += 1
                            potential_new_tags[tag_name]['task_ids'].append(task.id)
                            potential_new_tags[tag_name]['descriptions'].add(tag_info['desc'])
                            potential_new_tags[tag_name]['keywords_found'].add(keyword)
        
        # 6. 生成优化建议
        suggestions = []
        
        for tag_name, data in potential_new_tags.items():
            task_count = data['task_count']
            
            # 过滤条件
            if task_count < min_task_count:
                continue
            
            # 计算置信度（简单算法：基于任务数量）
            confidence = min(0.95, 0.6 + (task_count / 20))
            if confidence < min_confidence:
                continue
            
            # 合并描述
            unique_descriptions = list(data['descriptions'])
            
            suggestions.append({
                'type': 'new_tag',
                'tag_type': 'scene',
                'tag_name': tag_name,
                'description': unique_descriptions[0] if unique_descriptions else '',
                'task_count': task_count,
                'task_ids': data['task_ids'][:5],
                'confidence': confidence,
                'reason': f'在{days if not analyze_all else "所有历史"}数据中，发现 {task_count} 个任务包含相关元素（{", ".join(list(data["keywords_found"])[:3])}），置信度 {confidence:.2%}'
            })
        
        # 按任务数量和置信度排序
        suggestions.sort(key=lambda x: (x['task_count'], x['confidence']), reverse=True)
        
        # 7. 生成报告
        total_tasks = db.query(Tasks).filter(
            Tasks.status == 'completed',
            time_filter if time_filter is not None else True
        ).count()
        
        report = {
            'time_range': f'近 {days} 天' if not analyze_all else '所有历史数据',
            'total_tasks_analyzed': total_tasks,
            'tag_usage_stats': [{'tag': tag, 'count': count} for tag, count in tag_stats],
            'top_5_tags': sorted(tag_stats, key=lambda x: x[1], reverse=True)[:5],
            'low_usage_tags': [
                {'tag': tag, 'count': count} 
                for tag, count in tag_stats 
                if count < 5
            ],
            'potential_new_tags': suggestions,
            'current_pool_version': scene_pool['version'],
            'summary': {
                'existing_tags_count': len(tag_stats),
                'new_tags_found': len(suggestions),
                'low_usage_tags_count': len([t for t in tag_stats if t[1] < 5]),
                'total_suggestions': len(suggestions)
            }
        }
        
        return report, suggestions
        
    finally:
        db.close()


def apply_updates(
    suggestions: List[Dict],
    activate_immediately: bool = True,
    batch_retag: bool = True,
    batch_size: int = 100
) -> Dict:
    """应用标签更新
    
    Args:
        suggestions: 建议列表
        activate_immediately: 是否立即激活新版本
        batch_retag: 是否批量重打标
        batch_size: 批量重打标的批次大小
    
    Returns:
        更新结果
    """
    print("\n✅ 开始应用更新...")
    
    # 1. 加载当前标签池
    scene_pool = TagPoolManager.get_tags("scene")
    current_version = scene_pool['version']
    current_tags = scene_pool['tags']
    
    # 2. 过滤建议（只接受 new_tag 类型的建议）
    new_tags = []
    for suggestion in suggestions:
        if suggestion['type'] == 'new_tag' and suggestion['tag_type'] == 'scene':
            # 检查是否已存在
            existing_names = [tag['name'] for tag in current_tags]
            if suggestion['tag_name'] not in existing_names:
                new_tags.append({
                    'name': suggestion['tag_name'],
                    'desc': suggestion['description']
                })
                print(f"   + 新增标签: {suggestion['tag_name']}")
    
    if not new_tags:
        print("   ⚠️  没有新标签需要添加")
        return {
            "success": True,
            "new_version": None,
            "added_count": 0,
            "message": "没有新标签需要添加"
        }
    
    # 3. 合并新旧标签
    updated_tags = current_tags + new_tags
    
    # 4. 创建新版本
    new_pool = TagPoolManager.create_new_version(
        pool_type="scene",
        tags=updated_tags,
        from_version=current_version,
        created_by="system"  # 这里应该是实际的用户ID
    )
    
    new_version = new_pool['version']
    print(f"\n✅ 标签池已更新至版本 {new_version}")
    print(f"   新增 {len(new_tags)} 个标签")
    
    # 5. 激活新版本
    if activate_immediately:
        success = TagPoolManager.activate_version(
            pool_type="scene",
            version=new_version,
            activated_by="system"
        )
        
        if success:
            print(f"   ✅ 版本 {new_version} 已激活")
        else:
            print(f"   ⚠️  版本 {new_version} 激活失败")
    else:
        print(f"   ℹ️  版本 {new_version} 已创建，但未激活")
        print(f"   使用命令激活: python scripts/activate_pool.py --version {new_version}")
    
    # 6. 批量重打标（占位符）
    retag_result = None
    if batch_retag and activate_immediately:
        retag_confirm = input("\n是否批量重打标旧任务？(y/n): ")
        if retag_confirm.lower() == 'y':
            retag_result = batch_retag_tasks(
                target_version=new_version,
                batch_size=batch_size
            )
        else:
            print("   ℹ️  跳过批量重打标")
    
    return {
        "success": True,
        "new_version": new_version,
        "added_count": len(new_tags),
        "retag_result": retag_result,
        "message": f"标签池已更新至版本 {new_version}"
    }


def batch_retag_tasks(
    target_version: int,
    from_version: Optional[int] = None,
    batch_size: int = 100
) -> Dict:
    """批量重打标任务（占位符实现）
    
    Args:
        target_version: 目标标签池版本
        from_version: 从哪个版本开始重打标（None表示所有旧版本）
        batch_size: 批量大小
    
    Returns:
        重打标结果
    """
    print(f"\n🔄 开始批量重打标...")
    print(f"   目标版本: {target_version}")
    print(f"   批量大小: {batch_size}")
    
    # 这里应该实现实际的批量重打标逻辑
    # 暂时返回模拟数据
    return {
        "success": True,
        "total_tasks": 0,
        "completed_tasks": 0,
        "failed_tasks": 0,
        "message": "批量重打标功能暂未实现（需要调用AI模型）"
    }


def main():
    parser = argparse.ArgumentParser(
        description='分析标签使用情况并生成优化建议',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 分析近30天（默认）
  python scripts/analyze_tags_enhanced.py
  
  # 分析近7天
  python scripts/analyze_tags_enhanced.py --days 7
  
  # 分析所有历史数据
  python scripts/analyze_tags_enhanced.py --all
  
  # 自定义阈值
  python scripts/analyze_tags_enhanced.py --min-tasks 5 --min-conf 0.8
  
  # 自动应用更新
  python scripts/analyze_tags_enhanced.py --apply
        """
    )
    
    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='分析近N天的数据（默认30天）'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='分析所有历史数据'
    )
    parser.add_argument(
        '--min-tasks',
        type=int,
        default=3,
        help='最小任务数阈值（默认3）'
    )
    parser.add_argument(
        '--min-conf',
        type=float,
        default=0.7,
        help='最小置信度阈值（默认0.7）'
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='自动应用更新（跳过确认）'
    )
    parser.add_argument(
        '--no-activate',
        action='store_true',
        help='不立即激活新版本'
    )
    parser.add_argument(
        '--no-retag',
        action='store_true',
        help='不批量重打标'
    )
    
    args = parser.parse_args()
    
    # 执行分析
    report, suggestions = analyze_tags(
        days=args.days,
        analyze_all=args.all,
        min_task_count=args.min_tasks,
        min_confidence=args.min_conf
    )
    
    # 打印报告
    print("\n" + "="*70)
    print("📊 标签分析报告")
    print("="*70)
    print(f"\n时间范围: {report['time_range']}")
    print(f"分析任务数: {report['total_tasks_analyzed']}")
    print(f"当前版本: v{report['current_pool_version']}")
    print(f"现有标签数: {report['summary']['existing_tags_count']}")
    print(f"发现新标签: {report['summary']['new_tags_found']}")
    print(f"低频标签数: {report['summary']['low_usage_tags_count']}")
    
    print(f"\n🏆 Top 5 使用频率:")
    for i, tag in enumerate(report['top_5_tags'], 1):
        print(f"   {i}. {tag[0]}: {tag[1]} 次")
    
    if report['low_usage_tags']:
        print(f"\n⚠️  低频标签（<5次）:")
        for tag in report['low_usage_tags']:
            print(f"   - {tag['tag']}: {tag['count']} 次")
    
    if suggestions:
        print(f"\n💡 发现 {len(suggestions)} 个新标签建议:")
        for i, s in enumerate(suggestions, 1):
            print(f"\n   [{i}] {s['tag_name']}")
            print(f"       描述: {s['description']}")
            print(f"       相关任务: {s['task_count']} 个")
            print(f"       置信度: {s['confidence']:.2%}")
            print(f"       原因: {s['reason']}")
        
        # 询问是否应用
        if not args.apply:
            print("\n" + "-"*70)
            confirm = input("是否应用这些更新？(y/n): ")
            if confirm.lower() == 'y':
                apply_updates(
                    suggestions,
                    activate_immediately=not args.no_activate,
                    batch_retag=not args.no_retag
                )
        else:
            print("\n🚀 自动应用更新...")
            apply_updates(
                suggestions,
                activate_immediately=not args.no_activate,
                batch_retag=not args.no_retag
            )
    else:
        print("\n✅ 未发现需要优化的标签")
    
    print("\n" + "="*70)


if __name__ == "__main__":
    main()
