"""Favorite image persistence and long-term storage."""
import base64
import logging
import mimetypes
import re
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from storage.database.shared.model import FavoriteImages, Tasks, Users
from storage.database.task_manager import TaskManager
from storage.storage_manager import StorageCategory, get_storage_manager

logger = logging.getLogger(__name__)

FAVORITE_URL_EXPIRE_SECONDS = 315360000  # 10 years
FAVORITE_MAX_BYTES = 80 * 1024 * 1024
COMMON_PREFIXES = ("favorites/", "site-assets/", "assets/", "avatars/", "uploads/", "temp/")
LONG_TERM_PREFIXES = ("favorites/", "site-assets/", "assets/", "avatars/")


class FavoriteImageAdd(BaseModel):
    user_id: str = Field(..., description="User ID")
    task_id: str = Field(..., description="Source task ID")
    image_index: int = Field(..., ge=0, description="Image index in task result")
    source_url: Optional[str] = Field(default=None, description="Original image URL")
    source_url_candidates: list[str] = Field(default_factory=list, description="Candidate display/source URLs used only for task-result matching")
    thumbnail_url: Optional[str] = Field(default=None, description="Thumbnail URL")
    workflow_id: Optional[str] = Field(default=None, description="Workflow ID")
    workflow_name: Optional[str] = Field(default=None, description="Workflow display name")
    model_name: Optional[str] = Field(default=None, description="Model name")
    parameter_snapshot: Optional[dict] = Field(default=None, description="Source task parameter snapshot")


class FavoriteImageRemove(BaseModel):
    user_id: str = Field(..., description="User ID")
    favorite_id: Optional[str] = Field(default=None, description="Favorite record ID")
    task_id: Optional[str] = Field(default=None, description="Source task ID")
    image_index: Optional[int] = Field(default=None, ge=0, description="Image index")


class FavoriteImageManager:
    """Manage user image favorites independently from task lifecycle."""

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def _verify_user(db: Session, user_id: str) -> tuple[bool, Optional[str], Optional[Users]]:
        has_permission, error_msg = TaskManager.verify_user_permission(db, user_id)
        if not has_permission:
            return False, error_msg, None
        user = db.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            return False, "User not found", None
        return True, None, user

    @staticmethod
    def _can_access_task(user: Users, task: Tasks) -> bool:
        if task.user_id == user.user_id:
            return True
        if task.team_id and user.team_id and task.team_id == user.team_id:
            return True
        if user.role == "admin":
            return True
        return False

    @staticmethod
    def _read_url_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    @classmethod
    def _read_first_url_list(cls, source: Dict[str, Any], *keys: str) -> list[str]:
        for key in keys:
            urls = cls._read_url_list(source.get(key))
            if urls:
                return urls
        return []

    @staticmethod
    def _is_image_file_type(file_type: Any) -> bool:
        if not isinstance(file_type, str):
            return False
        normalized = file_type.lower().strip().split("/", 1)[-1]
        return normalized in {"image", "png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff", "svg"}

    @classmethod
    def _read_image_urls_from_result(cls, task_result: Dict[str, Any]) -> list[str]:
        direct_urls = cls._read_first_url_list(task_result, "imageUrls", "image_urls")
        if direct_urls:
            return direct_urls

        files = task_result.get("files")
        if not isinstance(files, list):
            return []

        image_urls: list[str] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            url = item.get("file_url") or item.get("url")
            if not isinstance(url, str) or not url.strip():
                continue
            file_type = item.get("file_type") or item.get("type") or item.get("mime_type") or item.get("mimeType")
            if file_type and not cls._is_image_file_type(file_type):
                continue
            image_urls.append(url.strip())
        return image_urls

    @classmethod
    def _source_url_matches(cls, requested_url: str, canonical_url: str) -> bool:
        requested_key = cls._extract_common_file_key(requested_url)
        canonical_key = cls._extract_common_file_key(canonical_url)
        if requested_key and canonical_key:
            return requested_key == canonical_key
        return requested_url.strip() == canonical_url.strip()

    @classmethod
    def _read_candidate_urls(cls, favorite_in: FavoriteImageAdd) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()

        def append(value: Any) -> None:
            if not isinstance(value, str):
                return
            url = value.strip()
            if not url or url in seen:
                return
            seen.add(url)
            candidates.append(url)

        append(favorite_in.source_url)
        for value in favorite_in.source_url_candidates or []:
            append(value)
        append(favorite_in.thumbnail_url)
        return candidates

    @classmethod
    def _candidate_matches_index(
        cls,
        candidates: list[str],
        image_urls: list[str],
        thumbnail_urls: list[str],
        preview_urls: list[str],
        image_index: int,
    ) -> bool:
        if image_index < 0 or image_index >= len(image_urls):
            return False

        index_urls = [image_urls[image_index]]
        if image_index < len(thumbnail_urls):
            index_urls.append(thumbnail_urls[image_index])
        if image_index < len(preview_urls):
            index_urls.append(preview_urls[image_index])

        return any(
            cls._source_url_matches(candidate, index_url)
            for candidate in candidates
            for index_url in index_urls
        )

    @classmethod
    def _normalize_favorite_input_from_task(cls, favorite_in: FavoriteImageAdd, task: Tasks) -> FavoriteImageAdd:
        task_result = task.result if isinstance(task.result, dict) else {}
        image_urls = cls._read_image_urls_from_result(task_result)
        thumbnail_urls = cls._read_first_url_list(task_result, "thumbnailUrls", "thumbnail_urls")
        preview_urls = cls._read_first_url_list(task_result, "previewUrls", "preview_urls")
        requested_urls = cls._read_candidate_urls(favorite_in)
        resolved_image_index: Optional[int] = None

        if cls._candidate_matches_index(
            requested_urls,
            image_urls,
            thumbnail_urls,
            preview_urls,
            favorite_in.image_index,
        ):
            resolved_image_index = favorite_in.image_index

        if resolved_image_index is None and requested_urls:
            resolved_image_index = next(
                (
                    index
                    for index in range(len(image_urls))
                    if cls._candidate_matches_index(
                        requested_urls,
                        image_urls,
                        thumbnail_urls,
                        preview_urls,
                        index,
                    )
                ),
                None,
            )

        if resolved_image_index is None:
            raise ValueError("这张图片不在原任务结果中，暂时无法收藏")

        canonical_source_url = image_urls[resolved_image_index]

        canonical_thumbnail_url = (
            thumbnail_urls[resolved_image_index]
            if resolved_image_index < len(thumbnail_urls)
            else (
                preview_urls[resolved_image_index]
                if resolved_image_index < len(preview_urls)
                else favorite_in.thumbnail_url
            )
        )

        return favorite_in.model_copy(update={
            "image_index": resolved_image_index,
            "source_url": canonical_source_url,
            "thumbnail_url": canonical_thumbnail_url,
        })

    @staticmethod
    def _task_to_dict(task: Optional[Tasks]) -> Optional[dict]:
        if task is None:
            return None
        return {
            "id": task.id,
            "user_id": task.user_id,
            "team_id": task.team_id,
            "platform": task.platform,
            "platform_task_id": task.platform_task_id,
            "type": task.type,
            "status": task.status,
            "workflow_parameters": task.workflow_parameters,
            "parameter_snapshot": task.parameter_snapshot,
            "result": task.result,
            "error": task.error,
            "deduction_result": task.deduction_result,
            "user_friendly_message": task.user_friendly_message,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "completed_at": task.completed_at,
            "batch_id": task.batch_id,
            "connection_mode": task.connection_mode,
            "is_deleted": task.is_deleted,
        }

    @classmethod
    def _favorite_to_dict(cls, favorite: FavoriteImages, task: Optional[Tasks] = None) -> dict:
        return {
            "favorite_id": favorite.favorite_id,
            "user_id": favorite.user_id,
            "task_id": favorite.task_id,
            "image_index": favorite.image_index,
            "source_url": favorite.source_url,
            "stored_url": favorite.stored_url,
            "file_key": favorite.file_key,
            "thumbnail_url": favorite.thumbnail_url,
            "workflow_id": favorite.workflow_id,
            "workflow_name": favorite.workflow_name,
            "model_name": favorite.model_name,
            "created_at": int(favorite.created_at or 0),
            "parameter_snapshot": favorite.parameter_snapshot,
            "task": cls._task_to_dict(task),
        }

    @staticmethod
    def _extract_common_file_key(value: str) -> Optional[str]:
        text = (value or "").strip()
        if not text:
            return None
        if not re.match(r"^[a-z][a-z0-9+.-]*://", text, re.I):
            key = text.replace("\\", "/").lstrip("/")
            return key if key.startswith(COMMON_PREFIXES) else None

        parsed = urlparse(text)
        query = parse_qs(parsed.query or "")
        for param in ("path", "file_key", "key"):
            raw_values = query.get(param)
            if raw_values:
                key = unquote(raw_values[0]).replace("\\", "/").lstrip("/")
                if key.startswith(COMMON_PREFIXES):
                    return key

        path = unquote(parsed.path or "").replace("\\", "/").lstrip("/")
        for prefix in COMMON_PREFIXES:
            index = path.find(prefix)
            if index >= 0:
                return path[index:]
        return None

    @staticmethod
    def _is_long_term_key(file_key: Optional[str]) -> bool:
        return bool(file_key and file_key.startswith(LONG_TERM_PREFIXES))

    @staticmethod
    def _extension_for_content_type(content_type: str) -> str:
        extension = mimetypes.guess_extension((content_type or "").split(";")[0].strip())
        if extension == ".jpe":
            return ".jpg"
        return extension or ".bin"

    @classmethod
    def _download_source(cls, source_url: str, task_id: str, image_index: int) -> tuple[bytes, str, str]:
        source = (source_url or "").strip()
        if not source:
            raise ValueError("Missing source_url")

        if source.startswith("data:"):
            header, _, encoded = source.partition(",")
            if not encoded:
                raise ValueError("Invalid data URL")
            content_type = "application/octet-stream"
            header_type = header[5:].split(";", 1)[0]
            if header_type:
                content_type = header_type
            content = base64.b64decode(encoded) if ";base64" in header else unquote(encoded).encode("utf-8")
            if len(content) > FAVORITE_MAX_BYTES:
                raise ValueError("Favorite image is too large")
            file_name = f"favorite_{task_id}_{image_index}{cls._extension_for_content_type(content_type)}"
            return content, file_name, content_type

        parsed = urlparse(source)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("source_url must be http(s) or data URL")

        request = urllib.request.Request(source, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=45) as response:
            content_type = response.headers.get("Content-Type") or "application/octet-stream"
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > FAVORITE_MAX_BYTES:
                raise ValueError("Favorite image is too large")

            chunks = []
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > FAVORITE_MAX_BYTES:
                    raise ValueError("Favorite image is too large")

        file_name = Path(unquote(parsed.path)).name or f"favorite_{task_id}_{image_index}"
        if "." not in file_name:
            file_name = f"{file_name}{cls._extension_for_content_type(content_type)}"
        return b"".join(chunks), file_name, content_type

    @classmethod
    def _store_source(cls, favorite_in: FavoriteImageAdd) -> tuple[Optional[str], str]:
        storage_mgr = get_storage_manager()
        existing_key = cls._extract_common_file_key(favorite_in.source_url)
        if existing_key and storage_mgr.storage.file_exists(file_key=existing_key):
            if cls._is_long_term_key(existing_key):
                stored_url = storage_mgr.storage.generate_presigned_url(
                    key=existing_key,
                    expire_time=FAVORITE_URL_EXPIRE_SECONDS,
                )
                return existing_key, stored_url
            content = storage_mgr.storage.read_file(file_key=existing_key)
            if len(content) > FAVORITE_MAX_BYTES:
                raise ValueError("Favorite image is too large")
            file_name = Path(existing_key).name or f"favorite_{favorite_in.task_id}_{favorite_in.image_index}"
            content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        else:
            content, file_name, content_type = cls._download_source(
                favorite_in.source_url,
                favorite_in.task_id,
                favorite_in.image_index,
            )
        upload_result = storage_mgr.upload_with_category(
            file_content=content,
            file_name=file_name,
            category=StorageCategory.FAVORITE,
            content_type=content_type,
            metadata={
                "source": "favorite_image",
                "user_id": favorite_in.user_id,
                "task_id": favorite_in.task_id,
                "image_index": str(favorite_in.image_index),
            },
        )
        return upload_result.get("file_key"), upload_result.get("url")

    def add_favorite_image(self, db: Session, favorite_in: FavoriteImageAdd) -> tuple[bool, Optional[dict], Optional[str]]:
        ok, error_msg, user = self._verify_user(db, favorite_in.user_id)
        if not ok or not user:
            return False, None, error_msg

        task = db.query(Tasks).filter(Tasks.id == favorite_in.task_id).first()
        if not task:
            return False, None, "Task not found"
        if not self._can_access_task(user, task):
            return False, None, "No permission to favorite this task image"

        try:
            favorite_in = self._normalize_favorite_input_from_task(favorite_in, task)
        except ValueError as error:
            return False, None, str(error)

        existing = db.query(FavoriteImages).filter(
            FavoriteImages.user_id == favorite_in.user_id,
            FavoriteImages.task_id == favorite_in.task_id,
            FavoriteImages.image_index == favorite_in.image_index,
        ).first()
        if existing:
            return True, self._favorite_to_dict(existing, task), None

        file_key, stored_url = self._store_source(favorite_in)
        if not stored_url:
            return False, None, "Failed to store favorite image"

        favorite = FavoriteImages(
            favorite_id=str(uuid.uuid4()),
            user_id=favorite_in.user_id,
            task_id=favorite_in.task_id,
            image_index=favorite_in.image_index,
            source_url=favorite_in.source_url,
            stored_url=stored_url,
            file_key=file_key,
            thumbnail_url=favorite_in.thumbnail_url,
            workflow_id=favorite_in.workflow_id,
            workflow_name=favorite_in.workflow_name,
            model_name=favorite_in.model_name,
            parameter_snapshot=favorite_in.parameter_snapshot or task.parameter_snapshot,
            created_at=self._now_ms(),
        )
        db.add(favorite)
        try:
            db.commit()
            db.refresh(favorite)
        except IntegrityError:
            db.rollback()
            existing = db.query(FavoriteImages).filter(
                FavoriteImages.user_id == favorite_in.user_id,
                FavoriteImages.task_id == favorite_in.task_id,
                FavoriteImages.image_index == favorite_in.image_index,
            ).first()
            if existing:
                return True, self._favorite_to_dict(existing, task), None
            raise
        except Exception:
            db.rollback()
            raise

        return True, self._favorite_to_dict(favorite, task), None

    def remove_favorite_image(self, db: Session, favorite_in: FavoriteImageRemove) -> tuple[bool, bool, Optional[str]]:
        ok, error_msg, _user = self._verify_user(db, favorite_in.user_id)
        if not ok:
            return False, False, error_msg

        query = db.query(FavoriteImages).filter(FavoriteImages.user_id == favorite_in.user_id)
        if favorite_in.favorite_id:
            query = query.filter(FavoriteImages.favorite_id == favorite_in.favorite_id)
        else:
            if not favorite_in.task_id or favorite_in.image_index is None:
                return False, False, "Missing favorite_id or task_id/image_index"
            query = query.filter(
                FavoriteImages.task_id == favorite_in.task_id,
                FavoriteImages.image_index == favorite_in.image_index,
            )

        favorite = query.first()
        if not favorite:
            return True, False, None

        db.delete(favorite)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        return True, True, None

    def list_favorite_images(
        self,
        db: Session,
        user_id: str,
        limit: int = 60,
        before_time: Optional[int] = None,
    ) -> tuple[bool, Optional[dict], Optional[str]]:
        ok, error_msg, _user = self._verify_user(db, user_id)
        if not ok:
            return False, None, error_msg

        safe_limit = min(max(int(limit or 60), 1), 100)
        query = db.query(FavoriteImages).filter(FavoriteImages.user_id == user_id)
        if before_time:
            query = query.filter(FavoriteImages.created_at < int(before_time))

        total = query.count()
        rows = query.order_by(FavoriteImages.created_at.desc()).limit(safe_limit + 1).all()
        has_more = len(rows) > safe_limit
        rows = rows[:safe_limit]

        task_ids = [row.task_id for row in rows]
        task_map: Dict[str, Tasks] = {}
        if task_ids:
            tasks = db.query(Tasks).filter(Tasks.id.in_(task_ids)).all()
            task_map = {task.id: task for task in tasks}

        favorites = [self._favorite_to_dict(row, task_map.get(row.task_id)) for row in rows]
        next_before_time = favorites[-1]["created_at"] if favorites else None
        return True, {
            "favorites": favorites,
            "items": favorites,
            "total": total,
            "limit": safe_limit,
            "has_more": has_more,
            "next_before_time": next_before_time,
        }, None
