"""RunningHub 响应转换工具"""
from typing import Any, Dict, List, Optional
import json


def convert_runninghub_to_task_update(runninghub_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 RunningHub 响应转换为任务更新格式
    
    Args:
        runninghub_response: RunningHub API 响应
        
    Returns:
        任务更新格式：{
            "status": "completed" | "failed",
            "result": {...},  # 成功时
            "error": {...},    # 失败时
            "completed_at": int
        }
    """
    code = runninghub_response.get("code")
    msg = runninghub_response.get("msg", "")
    data = runninghub_response.get("data", {})
    
    import time
    completed_at = int(time.time() * 1000)
    
    # 成功响应 (code === 0)
    if code == 0:
        result_data = {
            "status": "completed",
            "completed_at": completed_at,
            "result": {
                "message": msg,
                "files": []
            }
        }
        
        # 处理文件列表
        if isinstance(data, list):
            for file_info in data:
                file_data = {
                    "file_url": file_info.get("fileUrl"),
                    "file_type": file_info.get("fileType"),
                    "task_cost_time": file_info.get("taskCostTime"),
                    "node_id": file_info.get("nodeId"),
                    "consume_coins": file_info.get("consumeCoins"),
                    "third_party_consume_money": file_info.get("thirdPartyConsumeMoney"),
                    "consume_money": file_info.get("consumeMoney")
                }
                result_data["result"]["files"].append(file_data)
        
        # 保留原始响应
        result_data["result"]["raw_response"] = runninghub_response
        
        return result_data
    
    # 失败响应 (code !== 0)
    else:
        error_data = {
            "status": "failed",
            "completed_at": completed_at,
            "error": {
                "code": code,
                "message": msg,
                "detail": {}
            }
        }
        
        # 处理失败详情
        if isinstance(data, dict):
            failed_reason = data.get("failedReason", {})
            if failed_reason:
                error_data["error"]["detail"] = {
                    "exception_type": failed_reason.get("exception_type"),
                    "node_name": failed_reason.get("node_name"),
                    "node_id": failed_reason.get("node_id"),
                    "exception_message": failed_reason.get("exception_message"),
                    "traceback": failed_reason.get("traceback"),
                    "current_inputs": failed_reason.get("current_inputs"),
                    "current_outputs": failed_reason.get("current_outputs")
                }
        
        # 保留原始响应
        error_data["error"]["raw_response"] = runninghub_response
        
        return error_data


def create_task_update_request(
    task_id: str,
    user_id: str,
    runninghub_response: Dict[str, Any]
) -> Dict[str, Any]:
    """
    创建完整的任务更新请求
    
    Args:
        task_id: 任务ID
        user_id: 用户ID
        runninghub_response: RunningHub API 响应
        
    Returns:
        完整的任务更新请求
    """
    # 转换 RunningHub 响应
    task_update = convert_runninghub_to_task_update(runninghub_response)
    
    # 构建完整请求
    request = {
        "call_type": "user_task_management",
        "input": {
            "operation_type": "update_task",
            "user_id": user_id,
            "task_id": task_id,
            "task_updates": {
                "status": task_update.get("status"),
                "completed_at": task_update.get("completed_at")
            }
        }
    }
    
    # 添加结果或错误信息
    if task_update.get("status") == "completed":
        request["input"]["task_updates"]["result"] = task_update.get("result")
    else:
        request["input"]["task_updates"]["error"] = json.dumps(task_update.get("error"), ensure_ascii=False)
    
    return request


# 示例使用
if __name__ == "__main__":
    # 成功响应示例
    success_response = {
        "code": 0,
        "msg": "success",
        "data": [
            {
                "fileUrl": "https://rh-images.xiaoyaoyou.com/de0db6f2564c8697b07df55a77f07be9/output/ComfyUI_00033_hpgko_1742822929.png",
                "fileType": "png",
                "taskCostTime": "83",
                "nodeId": "12",
                "thirdPartyConsumeMoney": None,
                "consumeMoney": None,
                "consumeCoins": "17"
            }
        ]
    }
    
    # 失败响应示例
    failure_response = {
        "code": 805,
        "msg": "APIKEY_TASK_STATUS_ERROR",
        "data": {
            "failedReason": {
                "current_outputs": "{}",
                "exception_type": "TypeError",
                "node_name": "SONIC_PreData",
                "current_inputs": "{}",
                "traceback": "[\"  File \\\"/workspace/ComfyUI/execution.py\\\", line 1208, in execute\\n    output_data, output_ui, has_subgraph, has_pending_tasks = await get_output_data(prompt_id, unique_id, obj, input_data_all, execution_block_cb=execution_block_cb, pre_execute_cb=pre_execute_cb, hidden_inputs=hidden_inputs)\\n\",\"  File \\\"/workspace/ComfyUI/execution.py\\\", line 366, in get_output_data\\n    return_values = await _async_map_node_over_list(prompt_id, unique_id, obj, input_data_all, obj.FUNCTION, allow_interrupt=True, execution_block_cb=execution_block_cb, pre_execute_cb=pre_execute_cb, hidden_inputs=hidden_inputs)\\n\",\"  File \\\"/workspace/ComfyUI/execution.py\\\", line 340, in _async_map_node_over_list\\n    await process_inputs(input_dict, i)\\n\",\"  File \\\"/workspace/ComfyUI/execution.py\\\", line 328, in process_inputs\\n    result = f(**inputs)\\n\"]",
                "node_id": "276",
                "exception_message": "SONIC_PreData.sampler_main() missing 2 required positional arguments: 'clip_vision' and 'vae'"
            }
        }
    }
    
    print("=== 成功响应转换 ===")
    success_update = convert_runninghub_to_task_update(success_response)
    print(json.dumps(success_update, ensure_ascii=False, indent=2))
    
    print("\n=== 失败响应转换 ===")
    failure_update = convert_runninghub_to_task_update(failure_response)
    print(json.dumps(failure_update, ensure_ascii=False, indent=2))
    
    print("\n=== 完整更新请求（成功） ===")
    success_request = create_task_update_request("task_001", "user_test_001", success_response)
    print(json.dumps(success_request, ensure_ascii=False, indent=2))
