import json
import os
from typing import Optional
from jinja2 import Template
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk import LLMClient

from graphs.state import ImageTaggingInput, ImageTaggingOutput


def image_tagging_node(state: ImageTaggingInput, config: RunnableConfig, runtime: Runtime[Context]) -> ImageTaggingOutput:
    """
    title: 图像标签生成
    desc: 使用视觉模型分析图像，生成场景标签和产品标签
    integrations: 大语言模型
    """
    ctx = runtime.context

    if not state.image_url:
        return ImageTaggingOutput(
            scene_tags=[],
            product_tags=[],
            success=False,
            error="未提供图像URL",
            task_id=state.task_id
        )

    try:
        # 读取配置文件
        cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH"), config['metadata']['llm_cfg'])
        with open(cfg_file, 'r') as fd:
            _cfg = json.load(fd)

        llm_config = _cfg.get("config", {})
        sp = _cfg.get("sp", "")
        up = _cfg.get("up", "")

        # 使用jinja2模板渲染提示词
        sp_tpl = Template(sp)
        system_prompt_content = sp_tpl.render()

        up_tpl = Template(up)
        user_prompt_content = up_tpl.render()

        # 初始化LLM客户端
        client = LLMClient(ctx=ctx)

        # 构造多模态消息
        messages = [
            SystemMessage(content=system_prompt_content),
            HumanMessage(content=[
                {
                    "type": "text",
                    "text": user_prompt_content
                },
                {
                    "type": "image_url",
                    "image_url": {"url": state.image_url}
                }
            ])
        ]

        # 调用模型
        response = client.invoke(
            messages=messages,
            model=llm_config.get("model"),
            temperature=llm_config.get("temperature", 0.3),
            max_tokens=llm_config.get("max_tokens", 500)
        )

        # 解析响应
        # 处理响应内容，可能是字符串或列表
        if isinstance(response.content, str):
            response_text = response.content.strip()
        elif isinstance(response.content, list):
            # 如果是列表，取第一个元素
            if len(response.content) > 0 and isinstance(response.content[0], str):
                response_text = response.content[0].strip()
            else:
                response_text = str(response.content)
        else:
            response_text = str(response.content)
        
        # 尝试解析JSON
        try:
            tags_data = json.loads(response_text)
            # 验证格式
            scene_tags = tags_data.get("scene_tags", [])
            product_tags = tags_data.get("product_tags", [])
            
            return ImageTaggingOutput(
                scene_tags=scene_tags,
                product_tags=product_tags,
                success=True,
                task_id=state.task_id
            )
        except json.JSONDecodeError:
            # JSON解析失败，返回默认空标签
            import logging
            logging.error(f"标签生成失败，JSON解析错误: {response_text}")
            return ImageTaggingOutput(
                scene_tags=[],
                product_tags=[],
                success=False,
                error="标签解析失败",
                task_id=state.task_id
            )

    except Exception as e:
        import logging
        logging.error(f"标签生成失败: {e}", exc_info=True)
        return ImageTaggingOutput(
            scene_tags=[],
            product_tags=[],
            success=False,
            error=str(e),
            task_id=state.task_id
        )
