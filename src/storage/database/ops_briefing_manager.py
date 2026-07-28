"""美国亚马逊运营晨报数据管理"""
import datetime
import hashlib
import re
import uuid
from collections import Counter
from typing import Any, Optional
from urllib.parse import urlparse

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

            summary = "今日暂无有效晨报数据。"
            action_items = ["检查本地采集器和 VPN 状态，确认是否已采集并上传公开资讯。"]
            status = "empty"
            if items:
                top_title = items[0]["title"]
                summary = f"今日已采集 {len(items)} 条美国 Amazon 公开资讯，重点关注：{top_title}。"
                action_items = [
                    "优先查看 Amazon 官方动态，确认是否需要调整站内运营内容。",
                    "将行业资讯中与 AI 购物、Amazon Business、广告相关的内容转成内部选题。",
                ]
                if not signals:
                    action_items.append("今天不输出确定选品结论，仅保留公开趋势观察。")
                status = "ready" if not warnings else "partial_failed"

            briefing = db.query(OpsDailyBriefings).filter(OpsDailyBriefings.briefing_date == date).first()
            payload = {
                "status": status,
                "summary": summary,
                "official_updates": official,
                "ecommerce_news": news,
                "product_signals": signals,
                "action_items": action_items,
                "warnings": warnings,
                "source_stats": source_stats,
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
