import ipaddress
import json
import logging
import os
import socket
import time
from typing import Optional
from urllib.parse import urlparse

import requests
from coze_coding_dev_sdk import LLMClient
from coze_coding_utils.runtime_ctx.context import Context
from jinja2 import Template
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

_CAPABILITY_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL_SECONDS = 300


class AgentIntentInput(BaseModel):
    """Agent 意图判断节点的输入"""
    operation_type: Optional[str] = Field(default=None, description="操作类型")
    prompt: Optional[str] = Field(default=None, description="用户原始需求")
    assets: list[dict] = Field(default_factory=list, description="用户已上传素材摘要列表")
    current_target: Optional[dict] = Field(default=None, description="前端当前已选目标")
    capability_hash: Optional[str] = Field(default=None, description="前端当前能力表哈希")
    capability_manifest_url: Optional[str] = Field(default=None, description="能力表获取地址")
    capability_manifest: Optional[dict] = Field(default=None, description="能力表快照")

    @field_validator("assets", mode="before")
    @classmethod
    def normalize_assets(cls, value: object) -> list[dict]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]


class AgentIntentOutput(BaseModel):
    """Agent 意图判断节点的输出"""
    response_data: dict = Field(default={}, description="统一响应数据")


def _get_text_content(content: object) -> str:
    """安全提取 LLM 响应文本内容"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return str(content)


def _load_llm_config(config: RunnableConfig) -> dict:
    metadata = config.get("metadata", {}) if isinstance(config, dict) else {}
    llm_cfg = metadata.get("llm_cfg")
    if not llm_cfg:
        raise ValueError("未配置 agent_intent 的 llm_cfg")

    workspace_path = os.getenv("COZE_WORKSPACE_PATH") or os.getcwd()
    cfg_file = os.path.join(workspace_path, llm_cfg)
    with open(cfg_file, "r", encoding="utf-8") as fd:
        return json.load(fd)


def _validate_manifest(manifest: dict) -> dict:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("capabilities"), list):
        raise ValueError("Agent 能力表格式无效")
    return manifest


def _normalise_hostname(hostname: str) -> str:
    return hostname.strip().lower().rstrip(".")


def _allowed_manifest_hosts() -> set[str]:
    raw_hosts = os.getenv("AGENT_CAPABILITY_MANIFEST_HOSTS", "")
    return {
        _normalise_hostname(host)
        for host in raw_hosts.split(",")
        if host.strip()
    }


def _hostname_matches_allowed(hostname: str, allowed_hosts: set[str]) -> bool:
    return any(hostname == allowed or hostname.endswith(f".{allowed}") for allowed in allowed_hosts)


def _is_blocked_ip(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text)
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _validate_manifest_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Agent 能力表地址协议不合法")
    if not parsed.hostname:
        raise ValueError("Agent 能力表地址缺少域名")

    hostname = _normalise_hostname(parsed.hostname)
    allowed_hosts = _allowed_manifest_hosts()
    if allowed_hosts and not _hostname_matches_allowed(hostname, allowed_hosts):
        raise ValueError("Agent 能力表地址不在允许域名内")
    if hostname == "localhost":
        raise ValueError("Agent 能力表地址不能指向本机")

    try:
        if _is_blocked_ip(hostname):
            raise ValueError("Agent 能力表地址不能指向私网或保留地址")
    except ValueError as exc:
        if "Agent 能力表地址" in str(exc):
            raise

    for info in socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80)):
        resolved_ip = info[4][0]
        if _is_blocked_ip(resolved_ip):
            raise ValueError("Agent 能力表地址解析到私网或保留地址")

    return url


def _fetch_capability_manifest(state: AgentIntentInput) -> dict:
    if isinstance(state.capability_manifest, dict):
        return _validate_manifest(state.capability_manifest)

    url = state.capability_manifest_url
    if not url:
        raise ValueError("未提供 Agent 能力表地址")
    safe_url = _validate_manifest_url(url)

    cached = _CAPABILITY_CACHE.get(safe_url)
    if cached:
        cached_at, cached_manifest = cached
        cached_hash = cached_manifest.get("capabilityHash")
        if state.capability_hash and cached_hash == state.capability_hash:
            return cached_manifest
        if not state.capability_hash and time.time() - cached_at < _CACHE_TTL_SECONDS:
            return cached_manifest

    response = requests.get(safe_url, timeout=8, allow_redirects=False)
    if 300 <= response.status_code < 400:
        raise ValueError("Agent 能力表地址不允许跳转")
    response.raise_for_status()
    manifest = _validate_manifest(response.json())
    _CAPABILITY_CACHE[safe_url] = (time.time(), manifest)
    return manifest


def _compact_parameters(parameters: object) -> list[dict]:
    if not isinstance(parameters, list):
        return []

    result: list[dict] = []
    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        item = {
            "id": parameter.get("id"),
            "apiFieldName": parameter.get("apiFieldName"),
            "label": parameter.get("label"),
            "type": parameter.get("type"),
            "defaultValue": parameter.get("defaultValue"),
        }
        options = parameter.get("options")
        if isinstance(options, list):
            item["options"] = [
                {
                    "label": option.get("label"),
                    "value": option.get("value"),
                }
                for option in options
                if isinstance(option, dict)
            ]
        result.append({k: v for k, v in item.items() if v is not None})
    return result


def _compact_capabilities(manifest: dict) -> list[dict]:
    capabilities = manifest.get("capabilities", [])
    result: list[dict] = []
    for capability in capabilities:
        if not isinstance(capability, dict):
            continue
        result.append({
            "intent": capability.get("intent"),
            "workflowId": capability.get("workflowId"),
            "name": capability.get("name"),
            "description": capability.get("description"),
            "category": capability.get("category"),
            "assetRequirements": capability.get("assetRequirements") or {},
            "parameters": _compact_parameters(capability.get("parameters")),
        })
    return result


def _parse_json_response(text: str) -> dict:
    content = text.strip()
    if "```" in content:
        content = "\n".join(
            line for line in content.splitlines()
            if not line.strip().startswith("```")
        ).strip()

    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        content = content[start:end + 1]

    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("Agent 返回不是 JSON 对象")
    return parsed


def _normalise_workflow_id(value: object, capabilities_by_id: dict[str, dict]) -> Optional[str]:
    if not isinstance(value, str) or not value:
        return None
    if value in capabilities_by_id:
        return value
    if value.startswith("workflow_"):
        suffix = value.removeprefix("workflow_")
        if suffix.isdigit():
            candidate = f"workflow_{int(suffix):02d}"
            if candidate in capabilities_by_id:
                return candidate
    return None


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _stable_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _capability_parameter_map(capability: dict) -> dict[str, dict]:
    parameters = capability.get("parameters")
    if not isinstance(parameters, list):
        return {}

    result: dict[str, dict] = {}
    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        for key in (parameter.get("id"), parameter.get("apiFieldName")):
            if isinstance(key, str) and key:
                result[key] = parameter
    return result


def _option_values(parameter: dict) -> set[str]:
    options = parameter.get("options")
    if not isinstance(options, list):
        return set()
    return {
        _stable_json(option.get("value"))
        for option in options
        if isinstance(option, dict) and "value" in option
    }


def _filter_parameter_overrides(value: object, capability: dict) -> dict:
    overrides = _as_dict(value)
    parameter_map = _capability_parameter_map(capability)
    if not overrides or not parameter_map:
        return {}

    result: dict = {}
    for key, raw_value in overrides.items():
        parameter = parameter_map.get(key)
        if not parameter:
            logger.warning("跳过未声明的 Agent 参数覆盖: %s", key)
            continue

        allowed_values = _option_values(parameter)
        if allowed_values and _stable_json(raw_value) not in allowed_values:
            logger.warning("跳过非法的 Agent 参数选项值: %s", key)
            continue

        result[key] = raw_value
    return result


def _filter_tool_input_overrides(value: object, capability: dict) -> dict:
    if capability.get("intent") != "tool":
        return {}

    overrides = _as_dict(value)
    result: dict = {}
    params = _filter_parameter_overrides(overrides.get("params"), capability)
    if params:
        result["params"] = params

    selection_parameter = _capability_parameter_map(capability).get("selection")
    if selection_parameter:
        allowed_selection_values = _option_values(selection_parameter)
        selection_value = overrides.get("selectionValue")
        if selection_value is not None and _stable_json(selection_value) in allowed_selection_values:
            result["selectionValue"] = selection_value

    return result


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _asset_label(kind: str) -> str:
    if kind == "image":
        return "图片"
    if kind == "audio":
        return "音频"
    if kind == "video":
        return "视频"
    return "文件"


def _asset_counts(assets: list[dict]) -> dict[str, int]:
    counts = {"image": 0, "audio": 0, "video": 0, "file": 0}
    for asset in assets:
        kind = asset.get("kind")
        if kind in counts:
            counts[kind] += 1
    return counts


def _computed_missing_requirements(capability: dict, assets: list[dict]) -> list[str]:
    requirements = _as_dict(capability.get("assetRequirements"))
    counts = _asset_counts(assets)
    missing: list[str] = []

    for kind in ("image", "audio", "video", "file"):
        required = requirements.get(kind)
        if isinstance(required, int) and required > counts.get(kind, 0):
            missing.append(f"需要先上传 {required} 个{_asset_label(kind)}素材")

    if requirements.get("mask") is True:
        missing.append("需要提供修复区域蒙版")

    return missing


def _merge_missing_requirements(llm_missing: object, computed_missing: list[str]) -> list[str]:
    result: list[str] = []
    for item in [*_as_string_list(llm_missing), *computed_missing]:
        if item not in result:
            result.append(item)
    return result


def _normalise_plan(parsed: dict, manifest: dict, state: AgentIntentInput) -> dict:
    capabilities = [
        capability for capability in manifest.get("capabilities", [])
        if isinstance(capability, dict) and isinstance(capability.get("workflowId"), str)
    ]
    capabilities_by_id = {capability["workflowId"]: capability for capability in capabilities}
    target = _as_dict(parsed.get("target"))
    workflow_id = _normalise_workflow_id(target.get("workflowId"), capabilities_by_id)
    if not workflow_id:
        raise ValueError("Agent 返回的 workflowId 不在能力表中")

    capability = capabilities_by_id[workflow_id]
    confidence = parsed.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = 0

    missing_requirements = _merge_missing_requirements(
        parsed.get("missing_requirements"),
        _computed_missing_requirements(capability, state.assets),
    )

    plan = {
        "plan_id": parsed.get("plan_id") if isinstance(parsed.get("plan_id"), str) else f"agent_intent_{int(time.time() * 1000)}",
        "target": {
            "intent": capability.get("intent"),
            "workflowId": workflow_id,
        },
        "confidence": max(0, min(1, float(confidence))),
        "reason": parsed.get("reason") if isinstance(parsed.get("reason"), str) else "",
        "parameter_overrides": _filter_parameter_overrides(parsed.get("parameter_overrides"), capability),
        "tool_input_overrides": _filter_tool_input_overrides(parsed.get("tool_input_overrides"), capability),
        "missing_requirements": missing_requirements,
        "should_execute": False,
        "capability_hash": manifest.get("capabilityHash") or state.capability_hash,
    }

    if isinstance(parsed.get("prompt"), str) and parsed["prompt"].strip():
        plan["prompt"] = parsed["prompt"].strip()

    return plan


def agent_intent_node(
    state: AgentIntentInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> AgentIntentOutput:
    """
    title: Agent 意图判断
    desc: 使用大语言模型根据用户需求、素材摘要和当前能力表选择前端应切换的功能
    integrations: 大语言模型
    """
    ctx = runtime.context

    if state.operation_type not in (None, "resolve_creation_intent"):
        return AgentIntentOutput(response_data={
            "code": 1,
            "msg": f"不支持的 Agent 操作: {state.operation_type}",
            "data": None,
        })

    prompt = (state.prompt or "").strip()
    if not prompt and not state.assets:
        return AgentIntentOutput(response_data={
            "code": 1,
            "msg": "请输入需求或上传素材后再使用 Agent",
            "data": None,
        })

    try:
        manifest = _fetch_capability_manifest(state)
        llm_cfg = _load_llm_config(config)
        llm_config = llm_cfg.get("config", {})
        system_prompt = Template(llm_cfg.get("sp", "")).render()
        user_prompt = Template(llm_cfg.get("up", "")).render({
            "prompt": prompt,
            "assets_json": json.dumps(state.assets, ensure_ascii=False, indent=2),
            "current_target_json": json.dumps(state.current_target or {}, ensure_ascii=False, indent=2),
            "capability_hash": manifest.get("capabilityHash") or state.capability_hash or "",
            "capabilities_json": json.dumps(_compact_capabilities(manifest), ensure_ascii=False, indent=2),
        })

        client = LLMClient(ctx=ctx)
        response = client.invoke(
            messages=[
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ],
            model=llm_config.get("model"),
            temperature=llm_config.get("temperature", 0.2),
            max_tokens=llm_config.get("max_tokens", 1200),
        )
        parsed = _parse_json_response(_get_text_content(response.content))
        plan = _normalise_plan(parsed, manifest, state)

        logger.info("Agent 意图判断成功: %s", plan.get("target"))
        return AgentIntentOutput(response_data={
            "code": 0,
            "msg": "Agent 意图判断成功",
            "data": plan,
        })

    except Exception as exc:
        logger.exception("Agent 意图判断失败")
        return AgentIntentOutput(response_data={
            "code": 1,
            "msg": f"Agent 意图判断失败: {str(exc)}",
            "data": None,
        })
