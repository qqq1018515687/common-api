"""美国亚马逊运营晨报数据管理"""
import datetime
import hashlib
import json
import logging
import os
import re
import uuid
from collections import Counter
from typing import Any, Optional
from urllib.parse import urlparse

from coze_coding_dev_sdk import LLMClient
from coze_coding_utils.runtime_ctx.context import new_context
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from storage.database.shared.model import OpsBriefingRawItems, OpsDailyBriefings


ALLOWED_SOURCE_DOMAINS = {
    "aboutamazon.com",
    "www.aboutamazon.com",
    "advertising.amazon.com",
    "sell.amazon.com",
    "www.marketplacepulse.com",
    "marketplacepulse.com",
    "www.junglescout.com",
    "junglescout.com",
    "www.helium10.com",
    "helium10.com",
    "trends.google.com",
}

OFFICIAL_SOURCE_NAMES = {"amazon news", "amazon ads", "amazon seller"}
OPS_BRIEFING_EDITOR_MODEL = os.getenv("OPS_BRIEFING_EDITOR_MODEL", "doubao-seed-2-0-lite-260215")
logger = logging.getLogger(__name__)


class OpsBriefingRawItemInput(BaseModel):
    title: str = Field(..., description="标题")
    source_name: str = Field(..., description="来源名称")
    source_type: str = Field(default="news", description="official/news/trend/product_signal")
    url: str = Field(..., description="原文链接")
    published_at: Optional[str] = Field(default=None, description="原文发布时间")
    collected_at: Optional[str] = Field(default=None, description="采集时间")
    category: str = Field(default="news", description="分类")
    credibility: str = Field(default="medium", description="可信度")
    summary: Optional[str] = Field(default=None, description="摘要")
    raw_payload: Optional[dict[str, Any]] = Field(default=None, description="原始扩展数据")


class OpsBriefingIngestInput(BaseModel):
    briefing_date: Optional[str] = Field(default=None, description="晨报日期 YYYY-MM-DD")
    collector_id: Optional[str] = Field(default=None, description="采集器标识")
    items: list[OpsBriefingRawItemInput] = Field(default_factory=list, description="采集条目")


class OpsDailyBriefingSaveInput(BaseModel):
    briefing_date: str = Field(..., description="晨报日期 YYYY-MM-DD")
    status: str = Field(default="ready", description="ready/empty/partial_failed")
    summary: Optional[str] = Field(default=None, description="中文一句话总结")
    official_updates: list[dict[str, Any]] = Field(default_factory=list, description="Amazon 官方动态")
    ecommerce_news: list[dict[str, Any]] = Field(default_factory=list, description="行业资讯快报")
    product_signals: list[dict[str, Any]] = Field(default_factory=list, description="公开选品信号")
    action_items: list[str] = Field(default_factory=list, description="今日建议动作")
    warnings: list[str] = Field(default_factory=list, description="数据质量提示")
    source_stats: dict[str, Any] = Field(default_factory=dict, description="来源统计")
    generated_at: Optional[str] = Field(default=None, description="生成时间")


def 当前北京时间日期() -> str:
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).date().isoformat()


def 解析时间(value: Optional[str]) -> Optional[datetime.datetime]:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(text)
        except Exception:
            return None


def 标准化域名(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def 是否允许来源(url: str) -> bool:
    domain = 标准化域名(url)
    return domain in ALLOWED_SOURCE_DOMAINS


def 清理文本(value: Optional[str], max_length: int) -> str:
    text = re.sub(r"\s+", " ", (value or "")).strip()
    return text[:max_length]


def 提取原文信息(item: dict[str, Any]) -> tuple[str, Optional[str]]:
    raw_payload = item.get("raw_payload") if isinstance(item.get("raw_payload"), dict) else {}
    original_title = 清理文本(raw_payload.get("original_title") or item.get("title"), 500)
    original_summary = 清理文本(raw_payload.get("original_summary") or item.get("summary"), 4000)
    return original_title, original_summary or None


def 提取JSON文本(text: str) -> str:
    trimmed = text.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", trimmed, re.I)
    if fenced:
        return fenced.group(1).strip()
    start = trimmed.find("{")
    end = trimmed.rfind("}")
    if start >= 0 and end > start:
        return trimmed[start:end + 1]
    return trimmed


def 提取模型文本(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return str(content)


def 构建原文可追溯条目(item: dict[str, Any], fallback_index: int) -> dict[str, Any]:
    original_title, original_summary = 提取原文信息(item)
    return {
        **item,
        "id": item.get("id") or f"item_{fallback_index}",
        "title": 清理文本(item.get("title"), 500),
        "summary": 清理文本(item.get("summary"), 4000) or None,
        "original_title": original_title,
        "original_summary": original_summary,
    }


def 构建降级中文条目(item: dict[str, Any], fallback_index: int) -> dict[str, Any]:
    traceable = 构建原文可追溯条目(item, fallback_index)
    source_name = traceable.get("source_name") or "公开来源"
    return {
        **traceable,
        "title": f"{source_name}: {traceable['original_title']}",
        "summary": f"原文摘要: {traceable['original_summary']}" if traceable.get("original_summary") else "暂无摘要，建议打开来源核对原文。",
        "operator_insight": "仅基于公开来源保留原文线索，生成模型不可用时不做额外判断。",
        "translation_status": "fallback_original",
    }


def 规范化编辑条目(original: dict[str, Any], edited: dict[str, Any], fallback_index: int) -> dict[str, Any]:
    base = 构建降级中文条目(original, fallback_index)
    if not isinstance(edited, dict):
        return base
    title = 清理文本(edited.get("title"), 500)
    summary = 清理文本(edited.get("summary"), 1200)
    insight = 清理文本(edited.get("operator_insight"), 500)
    return {
        **base,
        "title": title or base["title"],
        "summary": summary or base["summary"],
        "operator_insight": insight or base["operator_insight"],
        "translation_status": "generated_zh" if title or summary or insight else base["translation_status"],
    }


def 生成中文编辑稿(items: list[dict[str, Any]], warnings: list[str]) -> dict[str, Any]:
    fallback_items = [构建降级中文条目(item, index) for index, item in enumerate(items)]
    if not items:
        return {
            "summary": "今日暂无有效亚马逊晨报数据。",
            "items": [],
            "action_items": ["检查本地采集器和 VPN 状态，确认是否已采集并上传公开资讯。"],
            "warnings": warnings,
            "generation_method": "empty",
            "translation_model": None,
        }

    system_prompt = (
        "你是面向国内美国亚马逊运营团队的晨报中文编辑。"
        "你只处理用户提供的公开来源资料，不联网、不编造、不输出店铺后台、竞品后台或 ASIN 私有数据。"
        "任务是把英文标题和摘要翻译成自然中文，并提炼很短的运营解读。"
        "选品信号必须保守表达为值得调研，不能断言爆品或销量。"
        "严格返回 JSON，不要 Markdown。"
    )
    user_payload = []
    for item in items[:20]:
        original_title, original_summary = 提取原文信息(item)
        user_payload.append({
            "id": item.get("id"),
            "source_name": item.get("source_name"),
            "source_type": item.get("source_type"),
            "category": item.get("category"),
            "credibility": item.get("credibility"),
            "title": original_title,
            "summary": original_summary or "",
            "published_at": item.get("published_at"),
            "url": item.get("url"),
        })

    user_prompt = (
        "请根据以下美国 Amazon 公开资讯生成中文晨报 JSON。\n"
        "输出结构: {\"summary\":\"一句话中文总览\",\"items\":[{\"id\":\"原 id\",\"title\":\"中文标题\",\"summary\":\"中文摘要，1-2句\",\"operator_insight\":\"给国内运营看的动作或关注点，1句\"}],\"action_items\":[\"2-4条今日建议动作\"],\"warnings\":[\"必要的数据质量提醒\"]}\n"
        "要求: 保留 Amazon、Marketplace Pulse 等品牌名；不要添加原文没有的事实；标题和摘要必须中文可读。\n"
        f"资料:\n{json.dumps(user_payload, ensure_ascii=False, indent=2)}"
    )

    try:
        client = LLMClient(ctx=new_context("ops_briefing_editor"))
        response = client.invoke(
            messages=[SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)],
            model=OPS_BRIEFING_EDITOR_MODEL,
            temperature=0.15,
            max_tokens=3500,
        )
        parsed = json.loads(提取JSON文本(提取模型文本(response.content)))
        edited_by_id = {
            str(item.get("id")): item
            for item in parsed.get("items", [])
            if isinstance(item, dict) and item.get("id") is not None
        }
        edited_items = [
            规范化编辑条目(item, edited_by_id.get(str(item.get("id")), {}), index)
            for index, item in enumerate(items)
        ]
        parsed_warnings = [清理文本(value, 300) for value in parsed.get("warnings", []) if isinstance(value, str) and value.strip()]
        return {
            "summary": 清理文本(parsed.get("summary"), 1000) or f"今日已采集 {len(items)} 条美国 Amazon 公开资讯。",
            "items": edited_items,
            "action_items": [清理文本(value, 300) for value in parsed.get("action_items", []) if isinstance(value, str) and value.strip()] or ["优先查看 Amazon 官方动态，确认是否需要调整站内运营内容。"],
            "warnings": warnings + parsed_warnings,
            "generation_method": "llm_zh_editor",
            "translation_model": OPS_BRIEFING_EDITOR_MODEL,
        }
    except Exception as exc:
        logger.warning("亚马逊晨报中文编辑模型不可用，使用可追溯降级内容: %s", exc)
        return {
            "summary": f"今日已采集 {len(items)} 条美国 Amazon 公开资讯；中文编辑模型暂不可用，页面保留原文线索供核对。",
            "items": fallback_items,
            "action_items": [
                "优先查看 Amazon 官方动态，确认是否需要调整站内运营内容。",
                "中文编辑模型不可用时，请打开来源核对原文后再转成运营动作。",
            ],
            "warnings": warnings + ["中文编辑模型暂不可用，已保留原文标题和摘要，未生成确定性解读。"],
            "generation_method": "fallback_original",
            "translation_model": None,
        }


def 规范化可信度(value: str, source_name: str, url: str) -> str:
    text = (value or "").lower().strip()
    if text in {"high", "medium", "low"}:
        return text
    source_key = source_name.lower().strip()
    domain = 标准化域名(url)
    if source_key in OFFICIAL_SOURCE_NAMES or domain.endswith("amazon.com") or domain.endswith("aboutamazon.com"):
        return "high"
    return "medium"


def 生成原始资料ID(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return f"ops_raw_{digest}"


class OpsBriefingManager:
    @staticmethod
    def _raw_to_dict(item: OpsBriefingRawItems) -> dict[str, Any]:
        return {
            "id": item.id,
            "briefing_date": item.briefing_date,
            "title": item.title,
            "source_name": item.source_name,
            "source_type": item.source_type,
            "url": item.url,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "collected_at": item.collected_at.isoformat() if item.collected_at else None,
            "category": item.category,
            "credibility": item.credibility,
            "summary": item.summary,
            "collector_id": item.collector_id,
            "raw_payload": item.raw_payload or {},
        }

    @staticmethod
    def _briefing_to_dict(briefing: Optional[OpsDailyBriefings]) -> Optional[dict[str, Any]]:
        if not briefing:
            return None
        return {
            "id": briefing.id,
            "briefing_date": briefing.briefing_date,
            "status": briefing.status,
            "summary": briefing.summary,
            "official_updates": briefing.official_updates or [],
            "ecommerce_news": briefing.ecommerce_news or [],
            "product_signals": briefing.product_signals or [],
            "action_items": briefing.action_items or [],
            "warnings": briefing.warnings or [],
            "source_stats": briefing.source_stats or {},
            "generated_at": briefing.generated_at.isoformat() if briefing.generated_at else None,
            "created_at": briefing.created_at.isoformat() if briefing.created_at else None,
            "updated_at": briefing.updated_at.isoformat() if briefing.updated_at else None,
        }

    @staticmethod
    def ingest_raw_items(db: Session, ingest: OpsBriefingIngestInput) -> tuple[bool, dict[str, Any], Optional[str]]:
        try:
            briefing_date = ingest.briefing_date or 当前北京时间日期()
            valid_items: list[OpsBriefingRawItemInput] = []
            rejected: list[dict[str, str]] = []

            for item in ingest.items:
                title = 清理文本(item.title, 500)
                url = 清理文本(item.url, 2000)
                if not title or not url:
                    rejected.append({"url": url, "reason": "missing_title_or_url"})
                    continue
                if not 是否允许来源(url):
                    rejected.append({"url": url, "reason": "source_domain_not_allowed"})
                    continue
                valid_items.append(item)

            if not valid_items:
                return True, {"inserted": 0, "updated": 0, "rejected": rejected}, None

            inserted = 0
            updated = 0
            now = datetime.datetime.now(datetime.timezone.utc)

            for item in valid_items:
                url = 清理文本(item.url, 2000)
                record = db.query(OpsBriefingRawItems).filter(OpsBriefingRawItems.url == url).first()
                data = {
                    "briefing_date": briefing_date,
                    "title": 清理文本(item.title, 500),
                    "source_name": 清理文本(item.source_name, 120),
                    "source_type": 清理文本(item.source_type, 40) or "news",
                    "url": url,
                    "published_at": 解析时间(item.published_at),
                    "collected_at": 解析时间(item.collected_at) or now,
                    "category": 清理文本(item.category, 60) or "news",
                    "credibility": 规范化可信度(item.credibility, item.source_name, url),
                    "summary": 清理文本(item.summary, 4000) or None,
                    "raw_payload": item.raw_payload,
                    "collector_id": 清理文本(ingest.collector_id, 80) or None,
                    "updated_at": now,
                }
                if record:
                    for key, value in data.items():
                        setattr(record, key, value)
                    updated += 1
                else:
                    db.add(OpsBriefingRawItems(id=生成原始资料ID(url), created_at=now, **data))
                    inserted += 1

            db.commit()
            return True, {"inserted": inserted, "updated": updated, "rejected": rejected}, None
        except Exception as exc:
            db.rollback()
            return False, {}, f"保存运营晨报原始资料失败: {exc}"

    @staticmethod
    def list_raw_items(db: Session, briefing_date: Optional[str] = None) -> list[dict[str, Any]]:
        date = briefing_date or 当前北京时间日期()
        rows = db.query(OpsBriefingRawItems).filter(
            OpsBriefingRawItems.briefing_date == date,
        ).order_by(
            OpsBriefingRawItems.published_at.desc().nullslast(),
            OpsBriefingRawItems.collected_at.desc(),
        ).all()
        return [OpsBriefingManager._raw_to_dict(item) for item in rows]

    @staticmethod
    def generate_briefing(db: Session, briefing_date: Optional[str] = None) -> tuple[bool, dict[str, Any], Optional[str]]:
        try:
            date = briefing_date or 当前北京时间日期()
            items = OpsBriefingManager.list_raw_items(db, date)
            now = datetime.datetime.now(datetime.timezone.utc)
            source_stats = dict(Counter(item["source_name"] for item in items))
            official = [item for item in items if item["source_type"] == "official" or item["credibility"] == "high"][:6]
            news = [item for item in items if item not in official and item["source_type"] in {"news", "official"}][:8]
            signals = [item for item in items if item["source_type"] in {"trend", "product_signal"}][:6]

            warnings: list[str] = []
            if not items:
                warnings.append("今日暂无本地采集器上传的有效资讯。")
            if not signals:
                warnings.append("今日公开选品信号不足，暂不输出具体商品方向。")

            editor_result = 生成中文编辑稿(items, warnings)
            edited_by_id = {
                str(item.get("id")): item
                for item in editor_result.get("items", [])
                if isinstance(item, dict) and item.get("id") is not None
            }

            def 转为中文条目(source_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
                result: list[dict[str, Any]] = []
                for index, item in enumerate(source_items):
                    edited = edited_by_id.get(str(item.get("id")))
                    result.append(edited if edited else 构建降级中文条目(item, index))
                return result

            summary = editor_result.get("summary") or "今日暂无有效晨报数据。"
            action_items = editor_result.get("action_items") or ["检查本地采集器和 VPN 状态，确认是否已采集并上传公开资讯。"]
            warnings = editor_result.get("warnings") or warnings
            status = "empty"
            if items:
                if not signals:
                    action_items.append("今天不输出确定选品结论，仅保留公开趋势观察。")
                status = "ready" if not warnings else "partial_failed"

            briefing = db.query(OpsDailyBriefings).filter(OpsDailyBriefings.briefing_date == date).first()
            payload = {
                "status": status,
                "summary": summary,
                "official_updates": 转为中文条目(official),
                "ecommerce_news": 转为中文条目(news),
                "product_signals": 转为中文条目(signals),
                "action_items": action_items,
                "warnings": warnings,
                "source_stats": {
                    **source_stats,
                    "generation_method": editor_result.get("generation_method"),
                    "translation_model": editor_result.get("translation_model"),
                    "raw_item_count": len(items),
                },
                "generated_at": now,
                "updated_at": now,
            }
            if briefing:
                for key, value in payload.items():
                    setattr(briefing, key, value)
            else:
                briefing = OpsDailyBriefings(
                    id=f"ops_briefing_{date}_{uuid.uuid4().hex[:8]}",
                    briefing_date=date,
                    created_at=now,
                    **payload,
                )
                db.add(briefing)

            db.commit()
            db.refresh(briefing)
            return True, OpsBriefingManager._briefing_to_dict(briefing) or {}, None
        except Exception as exc:
            db.rollback()
            return False, {}, f"生成运营晨报失败: {exc}"

    @staticmethod
    def get_briefing(db: Session, briefing_date: Optional[str] = None) -> tuple[bool, Optional[dict[str, Any]], Optional[str]]:
        try:
            date = briefing_date or 当前北京时间日期()
            briefing = db.query(OpsDailyBriefings).filter(OpsDailyBriefings.briefing_date == date).first()
            return True, OpsBriefingManager._briefing_to_dict(briefing), None
        except Exception as exc:
            return False, None, f"查询运营晨报失败: {exc}"

    @staticmethod
    def save_briefing(db: Session, briefing_input: OpsDailyBriefingSaveInput) -> tuple[bool, dict[str, Any], Optional[str]]:
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            briefing = db.query(OpsDailyBriefings).filter(OpsDailyBriefings.briefing_date == briefing_input.briefing_date).first()
            payload = {
                "status": 清理文本(briefing_input.status, 20) or "ready",
                "summary": 清理文本(briefing_input.summary, 4000) or None,
                "official_updates": briefing_input.official_updates,
                "ecommerce_news": briefing_input.ecommerce_news,
                "product_signals": briefing_input.product_signals,
                "action_items": [清理文本(item, 300) for item in briefing_input.action_items if 清理文本(item, 300)],
                "warnings": [清理文本(item, 300) for item in briefing_input.warnings if 清理文本(item, 300)],
                "source_stats": briefing_input.source_stats,
                "generated_at": 解析时间(briefing_input.generated_at) or now,
                "updated_at": now,
            }
            if briefing:
                for key, value in payload.items():
                    setattr(briefing, key, value)
            else:
                briefing = OpsDailyBriefings(
                    id=f"ops_briefing_{briefing_input.briefing_date}_{uuid.uuid4().hex[:8]}",
                    briefing_date=briefing_input.briefing_date,
                    created_at=now,
                    **payload,
                )
                db.add(briefing)

            db.commit()
            db.refresh(briefing)
            return True, OpsBriefingManager._briefing_to_dict(briefing) or {}, None
        except Exception as exc:
            db.rollback()
            return False, {}, f"保存中文运营晨报失败: {exc}"
