import json
import os
from typing import Optional
from jinja2 import Template
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk import LLMClient

from graphs.state import RunningHubErrorAnalysisInput, RunningHubErrorAnalysisOutput


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
