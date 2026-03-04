#!/usr/bin/env python3
"""测试系统通知功能 - 通过工作流API"""
import requests
import json
import time

def test_notification_via_workflow():
    """通过工作流API测试通知功能"""
    base_url = "http://localhost:5000/run"

    print("=" * 60)
    print("测试系统通知功能 - 工作流API")
    print("=" * 60)

    current_time = int(time.time() * 1000)

    # 测试1: 创建通知
    print("\n测试1: 创建通知")
    print("-" * 40)
    create_payload = {
        "call_type": "notification_management",
        "input": {
            "operation_type": "create",
            "notification_data": {
                "type": "info",
                "title": "API测试通知",
                "content": "<p>通过API创建的测试通知</p>",
                "priority": "medium",
                "is_active": True,
                "start_time": current_time,
                "end_time": None,
                "dismissible": True,
                "link_url": "https://example.com",
                "target_audience": "all",
                "created_by": "api_test_001"
            }
        }
    }

    print(f"请求: {json.dumps(create_payload, indent=2)}")

    try:
        response = requests.post(base_url, json=create_payload, timeout=10)
        result = response.json()

        print(f"\n响应状态码: {response.status_code}")
        print(f"响应数据: {json.dumps(result, indent=2)}")

        if result.get("response_data", {}).get("data", {}).get("code") == 0:
            notification_id = result["response_data"]["data"]["data"]["id"]
            print(f"✅ 创建成功! 通知ID: {notification_id}")
        else:
            print(f"❌ 创建失败: {result}")
            return False

    except Exception as e:
        print(f"❌ 请求失败: {str(e)}")
        return False

    # 测试2: 获取有效通知
    print("\n" + "=" * 60)
    print("测试2: 获取有效通知")
    print("-" * 40)
    get_active_payload = {
        "call_type": "notification_management",
        "input": {
            "operation_type": "get_active",
            "current_time": current_time + 1000
        }
    }

    print(f"请求: {json.dumps(get_active_payload, indent=2)}")

    try:
        response = requests.post(base_url, json=get_active_payload, timeout=10)
        result = response.json()

        print(f"\n响应状态码: {response.status_code}")
        print(f"响应数据: {json.dumps(result, indent=2)}")

        if result.get("response_data", {}).get("data", {}).get("code") == 0:
            notifications = result["response_data"]["data"]["data"]["notifications"]
            total = result["response_data"]["data"]["data"]["total"]
            print(f"✅ 查询成功! 有效通知数量: {total}")

            for notif in notifications:
                print(f"   - ID: {notif['id']}, 标题: {notif['title']}, 类型: {notif['type']}, 优先级: {notif['priority']}")
        else:
            print(f"❌ 查询失败: {result}")
            return False

    except Exception as e:
        print(f"❌ 请求失败: {str(e)}")
        return False

    # 测试3: 获取所有通知
    print("\n" + "=" * 60)
    print("测试3: 获取所有通知")
    print("-" * 40)
    get_all_payload = {
        "call_type": "notification_management",
        "input": {
            "operation_type": "get_all"
        }
    }

    print(f"请求: {json.dumps(get_all_payload, indent=2)}")

    try:
        response = requests.post(base_url, json=get_all_payload, timeout=10)
        result = response.json()

        print(f"\n响应状态码: {response.status_code}")

        if result.get("response_data", {}).get("data", {}).get("code") == 0:
            notifications = result["response_data"]["data"]["data"]["notifications"]
            total = result["response_data"]["data"]["data"]["total"]
            print(f"✅ 查询成功! 所有通知数量: {total}")

            for notif in notifications:
                print(f"   - ID: {notif['id']}, 标题: {notif['title']}, 激活: {notif['is_active']}")
        else:
            print(f"❌ 查询失败: {result}")
            return False

    except Exception as e:
        print(f"❌ 请求失败: {str(e)}")
        return False

    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
    return True


if __name__ == "__main__":
    import sys
    success = test_notification_via_workflow()
    sys.exit(0 if success else 1)
