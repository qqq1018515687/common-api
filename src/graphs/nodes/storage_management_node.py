import base64
import json
import logging
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from storage.storage_manager import StorageCategory, get_storage_manager

logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES = {
    "avatars": StorageCategory.AVATAR,
    "avatar": StorageCategory.AVATAR,
    "uploads": StorageCategory.UPLOAD,
    "upload": StorageCategory.UPLOAD,
    "temp": StorageCategory.TEMP,
    "legacy": "legacy",
}
CONTROLLED_PREFIXES = ("uploads/", "temp/", "avatars/")
CLEANUP_PREFIXES = ("uploads/", "temp/")
LEGACY_CLEANUP_PREFIXES = ("upload/", "tmp/", "coze_storage_7592868590546845742/")
FOLDER_KEEP_NAME = ".keep"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
OFFICE_TO_PDF_TYPES = {
    "application/msword",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
OFFICE_TO_PDF_SUFFIXES = {".doc", ".docx", ".ppt", ".pptx"}
OFFICE_CONVERTER_URL = (os.getenv("OFFICE_CONVERTER_URL") or "").strip()
OFFICE_CONVERTER_TOKEN = (os.getenv("OFFICE_CONVERTER_TOKEN") or "").strip()
try:
    OFFICE_CONVERTER_TIMEOUT_SECONDS = max(10, int(os.getenv("OFFICE_CONVERTER_TIMEOUT_SECONDS", "120")))
except ValueError:
    OFFICE_CONVERTER_TIMEOUT_SECONDS = 120
ALLOWED_UPLOAD_EXTENSIONS = {
    "png", "jpg", "jpeg", "webp", "gif", "bmp", "svg",
    "mp3", "wav", "m4a", "aac", "ogg", "flac",
    "mp4", "mov", "webm", "avi", "mkv",
    "pdf", "txt", "md", "csv", "json", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
    "zip", "rar", "7z", "tar", "gz",
}
ALLOWED_UPLOAD_MIME_PREFIXES = ("image/", "audio/", "video/", "text/")
ALLOWED_UPLOAD_MIME_TYPES = {
    "application/pdf",
    "application/json",
    "application/zip",
    "application/x-zip-compressed",
    "application/x-rar-compressed",
    "application/x-7z-compressed",
    "application/gzip",
    "application/msword",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
}


class StorageManagementInput(BaseModel):
    operation_type: Optional[str] = Field(default=None, description="list_objects/get_object_metadata/regenerate_url/upload_object/create_folder/delete_object/cleanup_expired/check_office_conversion")
    file_key: Optional[str] = Field(default=None, description="对象 key")
    category: Optional[str] = Field(default=None, description="avatars/uploads/temp/legacy")
    prefix: Optional[str] = Field(default=None, description="对象前缀")
    folder_name: Optional[str] = Field(default=None, description="新建文件夹名称")
    file_name: Optional[str] = Field(default=None, description="上传文件名")
    content_type: Optional[str] = Field(default=None, description="上传文件 MIME")
    file_content_base64: Optional[str] = Field(default=None, description="上传文件 base64 内容")
    avoid_overwrite: Optional[bool] = Field(default=True, description="同名文件是否自动改名")
    size: Optional[int] = Field(default=None, description="上传文件大小")
    convert_to_pdf: bool = Field(default=False, description="是否将 Office 文档转换为 PDF 后上传")
    continuation_token: Optional[str] = Field(default=None, description="分页 token")
    limit: Optional[int] = Field(default=None, description="分页数量，1-1000")
    dry_run: Optional[bool] = Field(default=True, description="清理试运行")
    include_avatars: Optional[bool] = Field(default=False, description="清理时是否包含 avatars")
    reason: Optional[str] = Field(default=None, description="管理原因")
    operator_role: Optional[str] = Field(default=None, description="操作者角色")
    operator_user_id: Optional[str] = Field(default=None, description="操作者用户 ID")


class StorageManagementOutput(BaseModel):
    response_data: dict = Field(default={}, description="统一响应数据")


def _success(data: dict, msg: str = "操作成功") -> StorageManagementOutput:
    return StorageManagementOutput(response_data={"code": 0, "msg": msg, "data": data})


def _failure(msg: str, code: int = 400, error_code: str = "STORAGE_MANAGEMENT_ERROR") -> StorageManagementOutput:
    return StorageManagementOutput(response_data={"code": code, "error_code": error_code, "msg": msg, "data": None})


def _require_admin(state: StorageManagementInput) -> Optional[StorageManagementOutput]:
    if (state.operator_role or "").strip().lower() != "admin":
        return _failure("对象储存管理只允许管理员操作", code=403, error_code="ADMIN_REQUIRED")
    return None


def _normalize_limit(limit: Optional[int]) -> int:
    if limit is None:
        return 100
    return min(max(int(limit), 1), 1000)


def _normalize_category(category: Optional[str]) -> Optional[str]:
    if not category:
        return None
    text = category.strip().lower()
    if not text or text == "all":
        return None
    if text not in ALLOWED_CATEGORIES:
        raise ValueError("对象储存分类不合法")
    return text


def _prefix_for_category(category: Optional[str]) -> Optional[str]:
    normalized = _normalize_category(category)
    if not normalized or normalized == "legacy":
        return None
    storage_category = ALLOWED_CATEGORIES[normalized]
    return StorageCategory.get_prefix(storage_category) + "/"


def _validate_file_key(file_key: Optional[str]) -> str:
    key = (file_key or "").strip()
    if not key:
        raise ValueError("缺少 file_key")
    if key.startswith("/") or ".." in key or "//" in key or re.match(r"^[a-z][a-z0-9+.-]*://", key, re.I):
        raise ValueError("file_key 不合法")
    return key


def _normalize_prefix(prefix: Optional[str]) -> str:
    text = (prefix or "").strip().replace("\\", "/").lstrip("/")
    if not text:
        return ""
    if ".." in text or "//" in text or re.match(r"^[a-z][a-z0-9+.-]*://", text, re.I):
        raise ValueError("prefix 不合法")
    return text if text.endswith("/") else f"{text}/"


def _validate_folder_name(folder_name: Optional[str]) -> str:
    name = (folder_name or "").strip()
    if not name:
        raise ValueError("缺少 folder_name")
    if name.startswith("/") or "/" in name or "\\" in name or ".." in name or re.match(r"^[a-z][a-z0-9+.-]*://", name, re.I):
        raise ValueError("folder_name 不合法")
    if not re.match(r"^[A-Za-z0-9._\-\u4e00-\u9fff]+$", name):
        raise ValueError("folder_name 仅允许中英文、数字、点、下划线和短横线")
    return name


def _safe_file_name(file_name: Optional[str]) -> str:
    name = Path((file_name or "").strip()).name
    if not name:
        raise ValueError("缺少 file_name")
    if name in {".", ".."} or "/" in name or "\\" in name or ".." in name:
        raise ValueError("file_name 不合法")
    if not re.match(r"^[A-Za-z0-9._\-\u4e00-\u9fff ]+$", name):
        raise ValueError("file_name 包含不支持的字符")
    return name


def _validate_upload_type(file_name: str, content_type: Optional[str]) -> str:
    suffix = Path(file_name).suffix.lower().lstrip(".")
    if not suffix or suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError("当前文件类型不允许上传")
    normalized_type = (content_type or mimetypes.guess_type(file_name)[0] or "application/octet-stream").strip()
    mime_allowed = normalized_type in ALLOWED_UPLOAD_MIME_TYPES or normalized_type.startswith(ALLOWED_UPLOAD_MIME_PREFIXES)
    if not mime_allowed:
        raise ValueError("当前文件 MIME 类型不允许上传")
    return normalized_type


def _is_office_to_pdf_file(file_name: str, content_type: str) -> bool:
    suffix = Path(file_name).suffix.lower()
    return suffix in OFFICE_TO_PDF_SUFFIXES or content_type.lower() in OFFICE_TO_PDF_TYPES


def _pdf_name(file_name: str) -> str:
    path = Path(file_name)
    stem = path.stem or "office-document"
    return f"{stem}.pdf"


def _office_converter_endpoint() -> str:
    url = OFFICE_CONVERTER_URL.rstrip("/")
    if not url:
        raise RuntimeError("未配置 Office 转换服务 OFFICE_CONVERTER_URL")
    if not url.lower().startswith("https://"):
        raise RuntimeError("Office 转换服务 OFFICE_CONVERTER_URL 必须使用 HTTPS")
    if url.endswith("/convert-to-pdf"):
        return url
    return f"{url}/convert-to-pdf"


def _read_converter_error(text: str) -> str:
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except Exception:
        return text[:500]
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("error") or payload.get("message")
        if isinstance(detail, str):
            return detail
    return text[:500]


def _convert_office_to_pdf(file_content: bytes, file_name: str, content_type: str) -> Tuple[bytes, str, Dict[str, Any]]:
    if not OFFICE_CONVERTER_TOKEN:
        raise RuntimeError("未配置 Office 转换服务 OFFICE_CONVERTER_TOKEN")
    payload = {
        "file_name": file_name,
        "content_type": content_type,
        "file_content_base64": base64.b64encode(file_content).decode("ascii"),
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OFFICE_CONVERTER_TOKEN}",
    }
    request = urllib.request.Request(
        _office_converter_endpoint(),
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=OFFICE_CONVERTER_TIMEOUT_SECONDS) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = _read_converter_error(exc.read().decode("utf-8", errors="replace"))
        raise RuntimeError(f"Office 转换服务返回 {exc.code}: {detail or '未知错误'}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Office 转换服务不可用: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Office 转换服务请求超时") from exc
    except Exception as exc:
        raise RuntimeError(f"Office 转换服务请求失败: {exc}") from exc

    pdf_base64 = response_payload.get("file_content_base64") if isinstance(response_payload, dict) else None
    if not isinstance(pdf_base64, str) or not pdf_base64:
        raise RuntimeError("Office 转换服务未返回 PDF 内容")
    try:
        pdf_content = base64.b64decode(pdf_base64, validate=True)
    except Exception as exc:
        raise RuntimeError("Office 转换服务返回的 PDF 内容无效") from exc
    if not pdf_content:
        raise RuntimeError("Office 转换服务返回的 PDF 内容为空")

    return pdf_content, _pdf_name(file_name), {
        "file_name": file_name,
        "content_type": content_type,
        "size": len(file_content),
    }


def _decode_upload_content(content_base64: Optional[str], expected_size: Optional[int]) -> bytes:
    if not content_base64:
        raise ValueError("缺少 file_content_base64")
    try:
        content = base64.b64decode(content_base64, validate=True)
    except Exception as exc:
        raise ValueError("file_content_base64 解析失败") from exc
    if not content:
        raise ValueError("上传文件内容为空")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("单文件大小不能超过 10MB")
    if expected_size is not None and int(expected_size) != len(content):
        raise ValueError("上传文件大小与内容不一致")
    return content


def _is_controlled_key(file_key: str) -> bool:
    return file_key.startswith(CONTROLLED_PREFIXES) or file_key.startswith(LEGACY_CLEANUP_PREFIXES)


def _category_from_key(file_key: str) -> str:
    if file_key.startswith("avatars/"):
        return "avatars"
    if file_key.startswith("uploads/"):
        return "uploads"
    if file_key.startswith("temp/"):
        return "temp"
    return "legacy"


def _is_image_key(file_key: str) -> bool:
    return bool(re.search(r"\.(png|jpe?g|webp|gif|bmp|svg)$", file_key, re.I))


def _is_folder_keep_key(file_key: str) -> bool:
    return file_key.endswith(f"/{FOLDER_KEEP_NAME}")


def _storage_category_for_key(file_key: str) -> str:
    category = _category_from_key(file_key)
    if category == "avatars":
        return StorageCategory.AVATAR
    if category == "temp":
        return StorageCategory.TEMP
    return StorageCategory.UPLOAD


def _timestamp(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        if hasattr(value, "timestamp"):
            return int(value.timestamp())
        return int(value)
    except Exception:
        return None


def _object_summary(file_key: str, raw: Optional[Dict[str, Any]] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    raw = raw or {}
    metadata = metadata or {}
    created_at = metadata.get("created_at") or _timestamp(raw.get("last_modified"))
    expires_in = metadata.get("expires_in") or 0
    expires_at = int(created_at + expires_in) if created_at and expires_in else None
    is_permanent = bool(metadata.get("is_permanent"))
    is_expired = False if is_permanent else bool(expires_at and expires_at < int(time.time()))
    return {
        "key": file_key,
        "file_key": file_key,
        "category": metadata.get("category") or _category_from_key(file_key),
        "size": raw.get("size"),
        "last_modified": _timestamp(raw.get("last_modified")),
        "etag": raw.get("etag"),
        "content_type": raw.get("content_type") or ("image/*" if _is_image_key(file_key) else None),
        "source": metadata.get("source"),
        "original_filename": metadata.get("original_filename"),
        "created_at": created_at,
        "expires_at": expires_at,
        "is_expired": is_expired,
        "is_permanent": is_permanent,
        "metadata": metadata,
    }


def _folder_summary(prefix: str, children: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    normalized_prefix = _normalize_prefix(prefix)
    children = children or []
    name = normalized_prefix.rstrip("/").split("/")[-1] if normalized_prefix else ""
    size = 0
    last_modified = None
    created_at = None
    for child in children:
        child_size = child.get("size")
        if isinstance(child_size, int):
            size += child_size
        child_modified = _timestamp(child.get("last_modified"))
        if child_modified and (last_modified is None or child_modified > last_modified):
            last_modified = child_modified
        if child_modified and (created_at is None or child_modified < created_at):
            created_at = child_modified
    return {
        "name": name,
        "prefix": normalized_prefix,
        "path": normalized_prefix,
        "category": _category_from_key(normalized_prefix),
        "count": len(children),
        "size": size,
        "created_at": created_at,
        "last_modified": last_modified,
        "type": "folder",
    }


def _split_directory_entries(objects: List[Dict[str, Any]], current_prefix: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    folders: Dict[str, List[Dict[str, Any]]] = {}
    files: List[Dict[str, Any]] = []
    for item in objects:
        key = item.get("key") or item.get("file_key") or ""
        if current_prefix and not key.startswith(current_prefix):
            continue
        relative_key = key[len(current_prefix):] if current_prefix else key
        if not relative_key:
            continue
        slash_index = relative_key.find("/")
        if slash_index > 0:
            folder_prefix = f"{current_prefix}{relative_key[:slash_index]}/"
            folders.setdefault(folder_prefix, []).append(item)
            continue
        if relative_key == FOLDER_KEEP_NAME or _is_folder_keep_key(key):
            continue
        files.append(item)
    folder_entries = [_folder_summary(prefix, children) for prefix, children in folders.items()]
    folder_entries.sort(key=lambda folder: str(folder.get("name") or ""))
    files.sort(key=lambda file_item: str(file_item.get("key") or file_item.get("file_key") or ""))
    return folder_entries, files


def _list_raw_objects(storage_mgr: Any, prefix: Optional[str], limit: int, continuation_token: Optional[str]) -> Dict[str, Any]:
    storage = storage_mgr.storage
    client = storage._get_client()
    kwargs = {
        "Bucket": storage._resolve_bucket(None),
        "MaxKeys": limit,
    }
    if prefix:
        kwargs["Prefix"] = prefix
    if continuation_token:
        kwargs["ContinuationToken"] = continuation_token
    resp = client.list_objects_v2(**kwargs)
    objects: List[Dict[str, Any]] = []
    for item in resp.get("Contents", []) or []:
        key = item.get("Key")
        if not key:
            continue
        objects.append({
            "key": key,
            "size": item.get("Size"),
            "last_modified": item.get("LastModified"),
            "etag": item.get("ETag"),
        })
    return {
        "objects": objects,
        "is_truncated": bool(resp.get("IsTruncated")),
        "next_continuation_token": resp.get("NextContinuationToken"),
    }


def _list_objects(state: StorageManagementInput) -> StorageManagementOutput:
    storage_mgr = get_storage_manager()
    normalized_category = _normalize_category(state.category)
    category_prefix = _prefix_for_category(state.category)
    prefix = _normalize_prefix(state.prefix or category_prefix)
    if category_prefix and prefix and not prefix.startswith(category_prefix):
        prefix = _normalize_prefix(category_prefix + prefix.lstrip("/"))
    limit = _normalize_limit(state.limit)
    listed = _list_raw_objects(storage_mgr, prefix, limit, state.continuation_token)
    objects = []
    for raw in listed["objects"]:
        key = raw["key"]
        if normalized_category == "legacy" and key.startswith(CONTROLLED_PREFIXES):
            continue
        metadata = storage_mgr.get_file_metadata(key) or {}
        objects.append(_object_summary(key, raw=raw, metadata=metadata))
    folders, files = _split_directory_entries(objects, prefix or "")
    return _success({
        "objects": objects,
        "folders": folders,
        "files": files,
        "total": len(objects),
        "scanned": len(objects),
        "category": state.category,
        "prefix": prefix,
        "limit": limit,
        "is_truncated": listed["is_truncated"],
        "next_continuation_token": listed["next_continuation_token"],
    }, "查询成功")


def _put_object_with_metadata(storage_mgr: Any, key: str, body: bytes, content_type: str, metadata: Dict[str, str]) -> None:
    storage = storage_mgr.storage
    _validate_file_key(key)
    storage._get_client().put_object(
        Bucket=storage._resolve_bucket(None),
        Key=key,
        Body=body,
        ContentType=content_type,
        Metadata=metadata,
    )


def _unique_object_key(storage_mgr: Any, prefix: str, file_name: str, avoid_overwrite: bool) -> str:
    candidate = f"{prefix}{file_name}"
    if not avoid_overwrite or not storage_mgr.storage.file_exists(file_key=candidate):
        return candidate

    path = Path(file_name)
    stem = path.stem
    suffix = path.suffix
    for index in range(1, 1000):
        candidate = f"{prefix}{stem} ({index}){suffix}"
        if not storage_mgr.storage.file_exists(file_key=candidate):
            return candidate
    raise ValueError("同名文件过多，无法自动改名")


def _upload_object(state: StorageManagementInput) -> StorageManagementOutput:
    if not (state.reason or "").strip():
        return _failure("上传文件必须填写 reason", code=400, error_code="REASON_REQUIRED")

    prefix = _normalize_prefix(state.prefix)
    if not prefix or not prefix.startswith(CONTROLLED_PREFIXES):
        return _failure("上传目录不在允许管理范围", code=403, error_code="PREFIX_NOT_ALLOWED")

    file_name = _safe_file_name(state.file_name)
    content_type = _validate_upload_type(file_name, state.content_type)
    content = _decode_upload_content(state.file_content_base64, state.size)
    converted_from = None
    if state.convert_to_pdf and _is_office_to_pdf_file(file_name, content_type):
        content, file_name, converted_from = _convert_office_to_pdf(content, file_name, content_type)
        content_type = "application/pdf"
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("转换后的 PDF 不能超过 10MB")

    storage_mgr = get_storage_manager()
    key = _unique_object_key(storage_mgr, prefix, file_name, state.avoid_overwrite is not False)
    now = int(time.time())
    storage_category = _storage_category_for_key(key)
    expires_in = StorageCategory.get_expiry_days(storage_category) * 86400
    is_permanent = StorageCategory.is_permanent(storage_category)
    metadata = {
        "category": storage_category,
        "created_at": str(now),
        "expires_in": str(expires_in),
        "original_filename": file_name,
        "is_permanent": str(is_permanent),
        "source": "admin_storage_manager",
        "operator_user_id": state.operator_user_id or "",
        "converted_from_name": converted_from["file_name"] if converted_from else "",
        "converted_from_content_type": converted_from["content_type"] if converted_from else "",
    }
    _put_object_with_metadata(storage_mgr, key, content, content_type, metadata)
    url_expiry = 315360000 if is_permanent else 86400
    url = storage_mgr.storage.generate_presigned_url(key=key, expire_time=url_expiry)
    summary = _object_summary(
        key,
        raw={"size": len(content), "last_modified": now, "content_type": content_type},
        metadata={
            "category": storage_category,
            "created_at": now,
            "expires_in": expires_in,
            "original_filename": file_name,
            "is_permanent": is_permanent,
            "source": "admin_storage_manager",
            "operator_user_id": state.operator_user_id or "",
        },
    )
    summary["signed_url"] = url
    summary["url"] = url
    summary["public_url"] = url
    summary["file_name"] = file_name
    summary["converted_from"] = converted_from
    return _success({
        "object": summary,
        "file_key": key,
        "key": key,
        "url": url,
        "signed_url": url,
        "public_url": url,
        "expires_at": summary.get("expires_at"),
        "content_type": content_type,
        "size": len(content),
        "file_name": file_name,
        "converted_from": converted_from,
    }, "上传成功")


def _create_folder(state: StorageManagementInput) -> StorageManagementOutput:
    if not (state.reason or "").strip():
        return _failure("新建文件夹必须填写 reason", code=400, error_code="REASON_REQUIRED")

    prefix = _normalize_prefix(state.prefix)
    if not prefix or not prefix.startswith(CONTROLLED_PREFIXES):
        return _failure("新建目录不在允许管理范围", code=403, error_code="PREFIX_NOT_ALLOWED")

    folder_name = _validate_folder_name(state.folder_name)
    folder_prefix = _normalize_prefix(f"{prefix}{folder_name}/")
    keep_key = f"{folder_prefix}{FOLDER_KEEP_NAME}"
    storage_mgr = get_storage_manager()
    now = int(time.time())
    metadata = {
        "category": _category_from_key(folder_prefix),
        "created_at": str(now),
        "expires_in": "0",
        "original_filename": FOLDER_KEEP_NAME,
        "is_permanent": "True",
        "source": "admin_storage_manager_folder",
        "operator_user_id": state.operator_user_id or "",
    }
    if not storage_mgr.storage.file_exists(file_key=keep_key):
        _put_object_with_metadata(storage_mgr, keep_key, b"", "application/x-directory", metadata)
    folder = _folder_summary(folder_prefix, [{"key": keep_key, "size": 0, "last_modified": now}])
    return _success({"folder": folder, "file_key": keep_key}, "文件夹已创建")


def _get_object_metadata(state: StorageManagementInput) -> StorageManagementOutput:
    key = _validate_file_key(state.file_key)
    storage_mgr = get_storage_manager()
    metadata = storage_mgr.get_file_metadata(key) or {}
    exists = storage_mgr.storage.file_exists(file_key=key)
    if not exists:
        return _failure("对象不存在", code=404, error_code="OBJECT_NOT_FOUND")
    raw = {}
    try:
        storage = storage_mgr.storage
        head = storage._get_client().head_object(
            Bucket=storage._resolve_bucket(None),
            Key=key,
        )
        raw = {
            "size": head.get("ContentLength"),
            "last_modified": head.get("LastModified"),
            "etag": head.get("ETag"),
            "content_type": head.get("ContentType"),
        }
    except Exception as exc:
        logger.warning("读取对象 head 信息失败，降级返回元数据: %s", exc)
    return _success({"object": _object_summary(key, raw=raw, metadata=metadata)}, "查询成功")


def _regenerate_url(state: StorageManagementInput) -> StorageManagementOutput:
    key = _validate_file_key(state.file_key)
    storage_mgr = get_storage_manager()
    if storage_mgr.is_expired(key):
        return _failure("对象已过期，不能刷新签名 URL", code=400, error_code="OBJECT_EXPIRED")
    url = storage_mgr.regenerate_url(key)
    if not url:
        return _failure("刷新签名 URL 失败", code=500, error_code="REGENERATE_URL_FAILED")
    metadata = storage_mgr.get_file_metadata(key) or {}
    summary = _object_summary(key, metadata=metadata)
    return _success({"file_key": key, "url": url, "expires_at": summary.get("expires_at")}, "刷新成功")


def _validate_object(state: StorageManagementInput) -> StorageManagementOutput:
    key = _validate_file_key(state.file_key)
    prefix = _normalize_prefix(state.prefix)
    if not prefix:
        return _failure("缺少校验目录前缀", code=400, error_code="PREFIX_REQUIRED")
    if not key.startswith(prefix):
        return _failure("对象不在允许的临时目录内", code=403, error_code="KEY_NOT_ALLOWED")

    storage_mgr = get_storage_manager()
    if not storage_mgr.storage.file_exists(file_key=key):
        return _failure("对象不存在", code=404, error_code="OBJECT_NOT_FOUND")
    if storage_mgr.is_expired(key):
        return _failure("对象已过期", code=410, error_code="OBJECT_EXPIRED")

    metadata = storage_mgr.get_file_metadata(key) or {}
    owner_user_id = metadata.get("operator_user_id")
    if owner_user_id and state.operator_user_id and owner_user_id != state.operator_user_id:
        return _failure("无权访问该临时对象", code=403, error_code="OBJECT_FORBIDDEN")

    raw = {}
    try:
        storage = storage_mgr.storage
        head = storage._get_client().head_object(
            Bucket=storage._resolve_bucket(None),
            Key=key,
        )
        raw = {
            "size": head.get("ContentLength"),
            "last_modified": head.get("LastModified"),
            "etag": head.get("ETag"),
            "content_type": head.get("ContentType"),
        }
    except Exception as exc:
        logger.warning("读取对象 head 信息失败，降级返回元数据: %s", exc)

    summary = _object_summary(key, raw=raw, metadata=metadata)
    url_expiry = 315360000 if summary.get("is_permanent") else 86400
    url = storage_mgr.storage.generate_presigned_url(key=key, expire_time=url_expiry)
    summary["url"] = url
    summary["signed_url"] = url
    summary["public_url"] = url
    summary["file_name"] = summary.get("original_filename") or Path(key).name
    return _success({
        **summary,
        "key": key,
        "file_key": key,
        "url": url,
        "signed_url": url,
        "public_url": url,
    }, "对象可用")


def _delete_object(state: StorageManagementInput) -> StorageManagementOutput:
    key = _validate_file_key(state.file_key)
    if not (state.reason or "").strip():
        return _failure("删除对象必须填写 reason", code=400, error_code="REASON_REQUIRED")
    if not _is_controlled_key(key):
        return _failure("对象 key 不在允许管理范围", code=403, error_code="KEY_NOT_ALLOWED")
    storage_mgr = get_storage_manager()
    exists = storage_mgr.storage.file_exists(file_key=key)
    if not exists:
        return _success({"file_key": key, "deleted": False}, "对象不存在或已删除")
    storage_mgr.storage.delete_file(file_key=key)
    return _success({"file_key": key, "deleted": True}, "删除成功")


def _delete_folder(state: StorageManagementInput) -> StorageManagementOutput:
    prefix = _normalize_prefix(state.prefix or state.file_key)
    if not (state.reason or "").strip():
        return _failure("删除文件夹必须填写 reason", code=400, error_code="REASON_REQUIRED")
    if not prefix or not prefix.startswith(CONTROLLED_PREFIXES):
        return _failure("目录不在允许管理范围", code=403, error_code="PREFIX_NOT_ALLOWED")

    storage_mgr = get_storage_manager()
    listed = _list_raw_objects(storage_mgr, prefix, 1000, None)
    keys = [item["key"] for item in listed["objects"]]
    allowed_keep_key = f"{prefix}{FOLDER_KEEP_NAME}"
    non_keep_keys = [key for key in keys if key != allowed_keep_key]
    if listed["is_truncated"] or non_keep_keys:
        return _failure("文件夹非空，不能删除；请先删除文件夹内文件", code=409, error_code="FOLDER_NOT_EMPTY")

    if not storage_mgr.storage.file_exists(file_key=allowed_keep_key):
        return _success({"prefix": prefix, "file_key": allowed_keep_key, "deleted": False}, "文件夹不存在或已删除")

    storage_mgr.storage.delete_file(file_key=allowed_keep_key)
    return _success({"prefix": prefix, "file_key": allowed_keep_key, "deleted": True}, "文件夹已删除")


def _iter_cleanup_prefixes(include_avatars: bool) -> List[str]:
    prefixes = list(CLEANUP_PREFIXES) + list(LEGACY_CLEANUP_PREFIXES)
    if include_avatars:
        prefixes.append("avatars/")
    return prefixes


def _is_cleanup_prefix_allowed(prefix: str, include_avatars: bool) -> bool:
    allowed_prefixes = tuple(_iter_cleanup_prefixes(include_avatars))
    return prefix.startswith(allowed_prefixes)


def _cleanup_expired(state: StorageManagementInput) -> StorageManagementOutput:
    dry_run = state.dry_run is not False
    if not dry_run and not (state.reason or "").strip():
        return _failure("执行清理必须填写 reason", code=400, error_code="REASON_REQUIRED")

    storage_mgr = get_storage_manager()
    normalized_category = _normalize_category(state.category)
    category_prefix = _prefix_for_category(state.category)
    requested_prefix = (state.prefix or "").strip()
    if requested_prefix or category_prefix:
        prefixes = [requested_prefix or category_prefix]
    elif normalized_category == "legacy":
        prefixes = list(LEGACY_CLEANUP_PREFIXES)
    else:
        prefixes = _iter_cleanup_prefixes(bool(state.include_avatars))
    prefixes = [prefix for prefix in prefixes if prefix]
    for prefix in prefixes:
        if not _is_cleanup_prefix_allowed(prefix, bool(state.include_avatars)):
            return _failure("过期清理只允许处理 uploads/、temp/ 和旧兼容前缀；avatars/ 需显式允许", code=403, error_code="PREFIX_NOT_ALLOWED")

    result = {"scanned": 0, "expired": 0, "deleted": 0, "failed": 0, "dry_run": dry_run, "objects": [], "errors": []}
    now = int(time.time())

    for prefix in prefixes:
        if prefix.startswith("avatars/") and not state.include_avatars:
            continue
        token = None
        while True:
            listed = _list_raw_objects(storage_mgr, prefix, 1000, token)
            result["scanned"] += len(listed["objects"])
            for raw in listed["objects"]:
                key = raw["key"]
                try:
                    metadata = storage_mgr.get_file_metadata(key) or {}
                    summary = _object_summary(key, raw=raw, metadata=metadata)
                    expired = bool(summary.get("is_expired"))
                    if not metadata and key.startswith(LEGACY_CLEANUP_PREFIXES):
                        last_modified = summary.get("last_modified")
                        expired = bool(last_modified and last_modified + 30 * 86400 < now)
                        summary["is_expired"] = expired
                    if not expired:
                        continue
                    result["expired"] += 1
                    result["objects"].append(summary)
                    if not dry_run:
                        storage_mgr.storage.delete_file(file_key=key)
                        result["deleted"] += 1
                except Exception as exc:
                    result["failed"] += 1
                    result["errors"].append({"file_key": key, "error": str(exc)})
            if not listed["is_truncated"]:
                break
            token = listed["next_continuation_token"]
    return _success(result, "试运行完成" if dry_run else "清理完成")


def _check_office_conversion() -> StorageManagementOutput:
    health_url = OFFICE_CONVERTER_URL.rstrip("/")
    if health_url and not health_url.endswith("/health"):
        health_url = f"{health_url}/health"
    result = {
        "converter_url_configured": bool(OFFICE_CONVERTER_URL),
        "converter_token_configured": bool(OFFICE_CONVERTER_TOKEN),
        "health_url": health_url or None,
        "http_status": None,
        "response": None,
        "error": None,
    }
    try:
        if not health_url:
            raise RuntimeError("未配置 Office 转换服务 OFFICE_CONVERTER_URL")
        if not health_url.lower().startswith("https://"):
            raise RuntimeError("Office 转换服务 OFFICE_CONVERTER_URL 必须使用 HTTPS")
        with urllib.request.urlopen(health_url, timeout=10) as response:
            result["http_status"] = response.status
            response_text = response.read().decode("utf-8", errors="replace")
            try:
                result["response"] = json.loads(response_text)
            except Exception:
                result["response"] = response_text[:500]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return _success(result, "Office 转换服务检查完成")


def storage_management_node(
    state: StorageManagementInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> StorageManagementOutput:
    """
    title: 对象储存管理
    desc: 管理员查看、刷新和清理 common 对象存储内容
    integrations: 对象存储
    """
    void_context = runtime.context
    void_context

    admin_error = _require_admin(state)
    if admin_error:
        return admin_error

    try:
        operation_type = state.operation_type or "list_objects"
        if operation_type == "list_objects":
            return _list_objects(state)
        if operation_type == "get_object_metadata":
            return _get_object_metadata(state)
        if operation_type == "regenerate_url":
            return _regenerate_url(state)
        if operation_type == "validate_object":
            return _validate_object(state)
        if operation_type == "upload_object":
            return _upload_object(state)
        if operation_type == "create_folder":
            return _create_folder(state)
        if operation_type == "delete_object":
            return _delete_object(state)
        if operation_type == "delete_folder":
            return _delete_folder(state)
        if operation_type == "cleanup_expired":
            return _cleanup_expired(state)
        if operation_type == "check_office_conversion":
            return _check_office_conversion()
        return _failure(f"不支持的对象储存操作: {operation_type}", code=400, error_code="UNSUPPORTED_OPERATION")
    except ValueError as exc:
        return _failure(str(exc), code=400, error_code="INVALID_REQUEST")
    except Exception as exc:
        logger.exception("对象储存管理失败")
        return _failure(f"对象储存管理失败: {exc}", code=500, error_code="STORAGE_MANAGEMENT_FAILED")
