import json
import os
import re
from typing import Optional
from jinja2 import Template
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk import LLMClient

from graphs.state import RunningHubErrorAnalysisInput, RunningHubErrorAnalysisOutput


GENERIC_MESSAGES = {
    "生成失败，请重试",
    "生成失败，请稍后重试",
    "任务执行失败",
    "任务状态异常",
    "刷新页面查看最新状态",
    "任务可能已被中断或取消，请刷新页面查看最新状态",
}


def _get_text_content(content: object) -> str:
    """安全提取 LLM 响应文本内容"""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        if len(content) > 0 and isinstance(content[0], str):
            return " ".join(content)
        else:
            return " ".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
    return str(content)


def _safe_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _collect_error_text(value: object, depth: int = 0) -> str:
    if depth > 5 or value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join(_collect_error_text(item, depth + 1) for item in value)
    if isinstance(value, dict):
        keys = [
            "code", "msg", "message", "error", "error_message", "statusText",
            "failureStage", "stage", "exception_type", "node_name",
            "failedReason", "data", "raw", "raw_error",
        ]
        parts = []
        for key in keys:
            if key in value:
                parts.append(_collect_error_text(value.get(key), depth + 1))
        if not parts:
            parts = [_collect_error_text(item, depth + 1) for item in value.values()]
        return " ".join(part for part in parts if part)
    return str(value)


def _extract_node_name(error_response: dict, text: str) -> str:
    def find_node_name(value: object, depth: int = 0) -> str:
        if depth > 5 or value is None:
            return ""
        if isinstance(value, dict):
            direct = value.get("node_name") or value.get("nodeName")
            if direct:
                return _safe_text(direct)
            for item in value.values():
                found = find_node_name(item, depth + 1)
                if found:
                    return found
        if isinstance(value, list):
            for item in value:
                found = find_node_name(item, depth + 1)
                if found:
                    return found
        return ""

    nested_node_name = find_node_name(error_response)
    if nested_node_name:
        return nested_node_name

    failed_reason = error_response.get("failedReason") or error_response.get("failed_reason")
    if isinstance(failed_reason, dict):
        node_name = failed_reason.get("node_name") or failed_reason.get("nodeName")
        if node_name:
            return _safe_text(node_name)

    node_name = error_response.get("node_name") or error_response.get("nodeName")
    if node_name:
        return _safe_text(node_name)

    match = re.search(r"(?:节点|node)[:：\s]*([A-Za-z0-9_.\-/\u4e00-\u9fff]+)", text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _build_rule_based_result(error_response: dict) -> Optional[dict]:
    text = _collect_error_text(error_response)
    normalized = text.lower()
    node_name = _extract_node_name(error_response, text)
    platform = _safe_text(error_response.get("platform")) or "unknown"

    if (
        "loadimagefromurl" in normalized
        or "图片链接加载超时" in text
        or "access-control-allow-origin" in normalized
        or "cors" in normalized
        or "403" in normalized and ("image" in normalized or "图片" in text or "tos.coze" in normalized)
    ):
        return {
            "success": True,
            "error_code": error_response.get("code"),
            "error_message": error_response.get("msg") or error_response.get("message") or text[:300],
            "user_friendly_message": "参考图链接无法被生成服务读取。",
            "suggestion": "请重新上传图片后再试。",
            "error_category": "图片链接不可访问",
            "platform": platform,
            "node_name": node_name,
        }

    if "cuda out of memory" in normalized or "out of memory" in normalized or "显存" in text:
        return {
            "success": True,
            "error_code": error_response.get("code"),
            "error_message": error_response.get("msg") or text[:300],
            "user_friendly_message": "生成资源不足，任务被中断。",
            "suggestion": "请稍后重试或降低尺寸。",
            "error_category": "资源不足",
            "platform": platform,
            "node_name": node_name,
        }

    if "timeout" in normalized or "timed out" in normalized or "超时" in text:
        return {
            "success": True,
            "error_code": error_response.get("code"),
            "error_message": error_response.get("msg") or text[:300],
            "user_friendly_message": "任务执行超时，未生成结果。",
            "suggestion": "请稍后重新生成。",
            "error_category": "网络超时",
            "platform": platform,
            "node_name": node_name,
        }

    if "content policy" in normalized or "safety" in normalized or "审核" in text or "违规" in text:
        return {
            "success": True,
            "error_code": error_response.get("code"),
            "error_message": error_response.get("msg") or text[:300],
            "user_friendly_message": "内容未通过安全检查。",
            "suggestion": "请调整提示词或参考图。",
            "error_category": "内容审核未通过",
            "platform": platform,
            "node_name": node_name,
        }

    if node_name and ("exception" in normalized or "节点" in text or "node" in normalized):
        return {
            "success": True,
            "error_code": error_response.get("code"),
            "error_message": error_response.get("msg") or text[:300],
            "user_friendly_message": f"{node_name} 节点执行失败。",
            "suggestion": "请检查输入图片和参数。",
            "error_category": "节点执行异常",
            "platform": platform,
            "node_name": node_name,
        }

    if _safe_text(error_response.get("msg")) in GENERIC_MESSAGES and not node_name:
        return None

    return None


def runninghub_error_analysis_node(
    state: RunningHubErrorAnalysisInput,
    config: RunnableConfig,
    runtime: Runtime[Context]
) -> RunningHubErrorAnalysisOutput:
    """
    title: RunningHub 错误分析
    desc: 使用大语言模型分析 RunningHub 任务失败响应，生成用户友好的错误说明
    integrations: 大语言模型
    """
    ctx = runtime.context

    error_response = state.error_response
    if not error_response:
        return RunningHubErrorAnalysisOutput(
            result={
                "success": False,
                "error": "未提供错误响应数据",
                "user_friendly_message": "未收到错误信息，无法进行分析。"
            }
        )

    rule_based_result = _build_rule_based_result(error_response)
    if rule_based_result:
        return RunningHubErrorAnalysisOutput(result=rule_based_result)

    try:
        # 读取配置文件
        cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH"), config['metadata']['llm_cfg'])
        with open(cfg_file, 'r') as fd:
            _cfg = json.load(fd)

        llm_config = _cfg.get("config", {})
        sp = _cfg.get("sp", "")
        up = _cfg.get("up", "")

        # 使用 jinja2 模板渲染提示词
        sp_tpl = Template(sp)
        system_prompt_content = sp_tpl.render()

        up_tpl = Template(up)
        error_json_str = json.dumps(error_response, ensure_ascii=False, indent=2)
        user_prompt_content = up_tpl.render({"error_response": error_json_str})

        # 初始化 LLM 客户端
        client = LLMClient(ctx=ctx)

        # 构造消息
        messages = [
            SystemMessage(content=system_prompt_content),
            HumanMessage(content=user_prompt_content)
        ]

        # 调用模型
        response = client.invoke(
            messages=messages,
            model=llm_config.get("model"),
            temperature=llm_config.get("temperature", 0.3),
            max_tokens=llm_config.get("max_tokens", 1000)
        )

        # 安全提取响应文本
        response_text = _get_text_content(response.content).strip()

        # 尝试解析 JSON
        try:
            analysis_result = json.loads(response_text)
            return RunningHubErrorAnalysisOutput(
                result={
                    "success": True,
                    "error_code": error_response.get("code"),
                    "error_message": error_response.get("msg"),
                    "user_friendly_message": analysis_result.get("user_friendly_message", response_text),
                    "suggestion": analysis_result.get("suggestion", ""),
                    "error_category": analysis_result.get("error_category", "unknown")
                }
            )
        except json.JSONDecodeError:
            # 如果不是 JSON，直接用文本作为友好说明
            return RunningHubErrorAnalysisOutput(
                result={
                    "success": True,
                    "error_code": error_response.get("code"),
                    "error_message": error_response.get("msg"),
                    "user_friendly_message": response_text,
                    "suggestion": "",
                    "error_category": "unknown"
                }
            )

    except Exception as e:
        return RunningHubErrorAnalysisOutput(
            result={
                "success": False,
                "error": f"错误分析失败: {str(e)}",
                "user_friendly_message": "无法分析错误原因，请稍后重试或联系客服。"
            }
        )
