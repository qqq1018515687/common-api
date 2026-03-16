#!/usr/bin/env python3
"""
任务列表游标分页测试脚本
"""
import requests
import json

BASE_URL = "http://localhost:5000"

def test_list_tasks():
    """测试任务列表查询"""
    
    # 测试参数
    payload = {
        "call_type": "task_management",
        "input": {
            "operation_type": "list_tasks",
            "user_id": "test_user_004",
            "start_time": 1700000000000,
            "end_time": 1999999999999,
            "limit": 5
        }
    }
    
    print("=" * 60)
    print("📋 测试任务列表查询（第一页）")
    print("=" * 60)
    print(f"请求参数: {json.dumps(payload, indent=2, ensure_ascii=False)}")
    print()
    
    response = requests.post(f"{BASE_URL}/run", json=payload)
    result = response.json()
    
    print(f"状态码: {response.status_code}")
    print()
    
    # 检查关键字段
    data = result.get("response_data", {}).get("data", {})
    
    print("✅ 关键字段检查:")
    print(f"  - tasks 数量: {len(data.get('tasks', []))}")
    print(f"  - total: {data.get('total')}")
    print(f"  - limit: {data.get('limit')}")
    print(f"  - has_more: {data.get('has_more')} (类型: {type(data.get('has_more')).__name__})")
    print(f"  - next_before_time: {data.get('next_before_time')}")
    print()
    
    # 完整响应
    print("📄 完整响应:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 测试第二页
    if data.get("has_more") and data.get("next_before_time"):
        print()
        print("=" * 60)
        print("📋 测试第二页查询")
        print("=" * 60)
        
        payload["input"]["before_time"] = data["next_before_time"]
        print(f"before_time: {data['next_before_time']}")
        
        response2 = requests.post(f"{BASE_URL}/run", json=payload)
        result2 = response2.json()
        data2 = result2.get("response_data", {}).get("data", {})
        
        print(f"  - tasks 数量: {len(data2.get('tasks', []))}")
        print(f"  - has_more: {data2.get('has_more')}")
        print(f"  - next_before_time: {data2.get('next_before_time')}")
    
    return result


if __name__ == "__main__":
    test_list_tasks()
