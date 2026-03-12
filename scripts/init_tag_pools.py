#!/usr/bin/env python3
"""
初始化默认标签池

功能：
1. 创建默认的场景标签池
2. 创建默认的产品标签池
3. 将默认标签池存入数据库

使用方法：
    python scripts/init_tag_pools.py
"""

import sys
import os
import json
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from storage.database.tag_pool_manager import TagPoolManager


def init_default_pools():
    """初始化默认标签池"""
    
    # 默认场景标签
    default_scene_tags = [
        {"name": "座椅场景", "desc": "坐姿、椅子、沙发"},
        {"name": "睡眠场景", "desc": "床、卧室、睡眠"},
        {"name": "躺卧场景", "desc": "躺椅、沙发、躺卧"},
        {"name": "驾驶场景", "desc": "汽车内部、座椅"},
        {"name": "办公场景", "desc": "办公室、办公桌"},
        {"name": "客厅场景", "desc": "客厅、沙发"},
        {"name": "装饰场景", "desc": "蜡烛、台灯、温馨氛围"},
        {"name": "户外场景", "desc": "户外、风景"}
    ]
    
    # 默认产品标签
    default_product_tags = [
        {"name": "腰靠", "desc": "腰部支撑，适用于座椅场景"},
        {"name": "腿枕", "desc": "腿部支撑，适用于躺卧场景"},
        {"name": "融蜡灯", "desc": "氛围装饰，适用于装饰场景"},
        {"name": "脚垫", "desc": "脚部支撑，适用于驾驶、办公场景"},
        {"name": "枕头", "desc": "头部支撑，适用于睡眠、躺卧场景"},
        {"name": "坐垫", "desc": "臀部支撑，适用于座椅场景"}
    ]
    
    print("🚀 开始初始化默认标签池...\n")
    
    # 初始化场景标签池
    print("1. 初始化场景标签池...")
    scene_result = TagPoolManager.initialize_default_pool("scene", default_scene_tags)
    if scene_result["success"]:
        print(f"   ✅ {scene_result['message']}")
    else:
        print(f"   ℹ️  {scene_result['message']}")
    
    # 初始化产品标签池
    print("\n2. 初始化产品标签池...")
    product_result = TagPoolManager.initialize_default_pool("product", default_product_tags)
    if product_result["success"]:
        print(f"   ✅ {product_result['message']}")
    else:
        print(f"   ℹ️  {product_result['message']}")
    
    # 保存配置文件（可选）
    print("\n3. 保存配置文件...")
    config_dir = Path(os.path.join(os.path.dirname(__file__), '..', 'config', 'tag_pools'))
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存场景标签配置
    scene_config_file = config_dir / "scene_tags_v1.json"
    with open(scene_config_file, 'w', encoding='utf-8') as f:
        json.dump({
            "version": 1,
            "tags": default_scene_tags
        }, f, ensure_ascii=False, indent=2)
    print(f"   ✅ 已保存: {scene_config_file}")
    
    # 保存产品标签配置
    product_config_file = config_dir / "product_tags_v1.json"
    with open(product_config_file, 'w', encoding='utf-8') as f:
        json.dump({
            "version": 1,
            "tags": default_product_tags
        }, f, ensure_ascii=False, indent=2)
    print(f"   ✅ 已保存: {product_config_file}")
    
    print("\n" + "="*60)
    print("✅ 默认标签池初始化完成！")
    print("="*60)
    print("\n默认场景标签:")
    for tag in default_scene_tags:
        print(f"  - {tag['name']}: {tag['desc']}")
    
    print("\n默认产品标签:")
    for tag in default_product_tags:
        print(f"  - {tag['name']}: {tag['desc']}")
    
    print("\n可以使用以下命令分析标签使用情况:")
    print("  python scripts/analyze_tags_enhanced.py")


if __name__ == "__main__":
    init_default_pools()
