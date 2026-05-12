"""
缩略图生成工具
从原图 URL 下载 → Pillow 缩放 → 上传对象存储 → 返回缩略图 URL
"""
import os
import io
import time
import logging
import json
from typing import Optional, Dict, List, Any, Tuple

import httpx
from PIL import Image

from storage.storage_manager import StorageCategory

logger = logging.getLogger(__name__)

# 缩略图最大边长
THUMBNAIL_MAX_SIZE = 300

# 下载超时（秒）
DOWNLOAD_TIMEOUT = 30

# 支持生成缩略图的 MIME / 扩展名
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}

# 视频扩展名（暂不生成缩略图，跳过）
VIDEO_EXTENSIONS = {'.mp4', '.webm', '.avi', '.mov', '.mkv', '.wmv', '.flv'}

# 音频扩展名（暂不生成缩略图，跳过）
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.wma', '.aiff'}


def _get_storage_manager():
    """获取 StorageManager 实例"""
    from storage.storage_manager import get_storage_manager
    return get_storage_manager()


def _is_image_url(url: str) -> bool:
    """判断 URL 是否为图片（基于扩展名和 URL 路径）"""
    if not url:
        return False
    url_lower = url.lower().split("?")[0]  # 去掉查询参数
    return any(url_lower.endswith(ext) for ext in IMAGE_EXTENSIONS)


def _is_media_url(url: str) -> bool:
    """判断 URL 是否为可展示的媒体（图片/视频/音频）"""
    if not url:
        return False
    url_lower = url.lower().split("?")[0]
    all_exts = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
    return any(url_lower.endswith(ext) for ext in all_exts)


def _extract_image_urls_from_result(result: Any) -> List[str]:
    """
    从任务 result 中提取所有图片 URL
    
    支持的结构：
    1. result.files[].url
    2. result.url
    3. result.images[].url
    4. result.output.images[]
    """
    urls: List[str] = []
    
    if result is None:
        return urls
    
    # 如果 result 是字符串，尝试解析为 JSON
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return urls
    
    if not isinstance(result, dict):
        return urls
    
    # 1. result.files[]
    files = result.get("files")
    if isinstance(files, list):
        for f in files:
            if isinstance(f, dict):
                url = f.get("url")
                if url and isinstance(url, str) and _is_image_url(url):
                    urls.append(url)
    
    # 2. result.url
    url = result.get("url")
    if url and isinstance(url, str) and _is_image_url(url):
        urls.append(url)
    
    # 3. result.images[]
    images = result.get("images")
    if isinstance(images, list):
        for img in images:
            if isinstance(img, dict):
                url = img.get("url")
                if url and isinstance(url, str) and _is_image_url(url):
                    urls.append(url)
            elif isinstance(img, str) and _is_image_url(img):
                urls.append(img)
    
    # 4. result.output.images[]
    output = result.get("output")
    if isinstance(output, dict):
        output_images = output.get("images")
        if isinstance(output_images, list):
            for img in output_images:
                if isinstance(img, dict):
                    url = img.get("url")
                    if url and isinstance(url, str) and _is_image_url(url):
                        urls.append(url)
                elif isinstance(img, str) and _is_image_url(img):
                    urls.append(img)
    
    return urls


def _extract_all_media_urls_from_result(result: Any) -> List[str]:
    """从任务 result 中提取所有媒体 URL（图片/视频/音频），用于判断任务是否有可展示结果"""
    urls: List[str] = []
    
    if result is None:
        return urls
    
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return urls
    
    if not isinstance(result, dict):
        return urls
    
    files = result.get("files")
    if isinstance(files, list):
        for f in files:
            if isinstance(f, dict):
                url = f.get("url")
                if url and isinstance(url, str) and _is_media_url(url):
                    urls.append(url)
    
    url = result.get("url")
    if url and isinstance(url, str) and _is_media_url(url):
        urls.append(url)
    
    images = result.get("images")
    if isinstance(images, list):
        for img in images:
            if isinstance(img, dict):
                url = img.get("url")
                if url and isinstance(url, str) and _is_media_url(url):
                    urls.append(url)
            elif isinstance(img, str) and _is_media_url(img):
                urls.append(img)
    
    output = result.get("output")
    if isinstance(output, dict):
        output_images = output.get("images")
        if isinstance(output_images, list):
            for img in output_images:
                if isinstance(img, dict):
                    url = img.get("url")
                    if url and isinstance(url, str) and _is_media_url(url):
                        urls.append(url)
                elif isinstance(img, str) and _is_media_url(img):
                    urls.append(img)
    
    return urls


def generate_thumbnail(image_url: str, max_size: int = THUMBNAIL_MAX_SIZE) -> Optional[bytes]:
    """
    下载图片并生成缩略图
    
    Args:
        image_url: 原图 URL
        max_size: 缩略图最大边长（像素）
    
    Returns:
        缩略图 bytes（JPEG 格式），失败返回 None
    """
    try:
        with httpx.Client(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(image_url)
            resp.raise_for_status()
            image_data = resp.content
        
        img = Image.open(io.BytesIO(image_data))
        
        # 统一转 RGB（处理 RGBA/P 等）
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        
        # 等比缩放
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # 输出为 JPEG
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    
    except Exception as e:
        logger.warning(f"生成缩略图失败 [{image_url}]: {e}")
        return None


def upload_thumbnail(thumbnail_bytes: bytes, original_url: str) -> Optional[str]:
    """
    上传缩略图到对象存储
    
    Args:
        thumbnail_bytes: 缩略图数据
        original_url: 原图 URL（用于生成文件名）
    
    Returns:
        缩略图 URL，失败返回 None
    """
    try:
        storage_mgr = _get_storage_manager()
        
        # 从原始 URL 提取文件名
        url_path = original_url.split("?")[0]
        original_name = url_path.rstrip("/").rsplit("/", 1)[-1] if "/" in url_path else "image.jpg"
        thumb_name = f"thumb_{original_name}"
        
        upload_result = storage_mgr.upload_with_category(
            file_content=thumbnail_bytes,
            file_name=thumb_name,
            category=StorageCategory.THUMBNAIL,
            content_type="image/jpeg",
            acl="public-read"
        )
        
        url = upload_result.get("url")
        if url:
            logger.info(f"缩略图上传成功: {thumb_name} -> {url}")
        return url
    
    except Exception as e:
        logger.warning(f"缩略图上传失败 [{original_url}]: {e}")
        return None


def generate_and_upload_thumbnail(image_url: str, max_size: int = THUMBNAIL_MAX_SIZE) -> Optional[str]:
    """
    生成缩略图并上传，返回缩略图 URL
    
    Args:
        image_url: 原图 URL
        max_size: 缩略图最大边长
    
    Returns:
        缩略图 URL，失败返回 None
    """
    thumb_bytes = generate_thumbnail(image_url, max_size)
    if thumb_bytes is None:
        return None
    return upload_thumbnail(thumb_bytes, image_url)


def process_result_thumbnails(result: Any) -> Any:
    """
    处理任务 result，为图片 URL 生成缩略图并写入 previewUrl / previewUrls
    
    Args:
        result: 任务 result（dict 或 JSON 字符串）
    
    Returns:
        更新后的 result（与输入同类型），无变化时原样返回
    """
    if result is None:
        return result
    
    is_string = isinstance(result, str)
    if is_string:
        try:
            result_dict = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return result
    else:
        result_dict = result
    
    if not isinstance(result_dict, dict):
        return result
    
    # 已经有 previewUrl / previewUrls，跳过
    if result_dict.get("previewUrl") or result_dict.get("previewUrls"):
        return result
    
    image_urls = _extract_image_urls_from_result(result_dict)
    if not image_urls:
        return result
    
    preview_urls: List[str] = []
    for url in image_urls:
        thumb_url = generate_and_upload_thumbnail(url)
        if thumb_url:
            preview_urls.append(thumb_url)
        else:
            # 缩略图生成失败，退回原图
            preview_urls.append(url)
    
    if not preview_urls:
        return result
    
    # 写入 result
    result_dict["previewUrls"] = preview_urls
    if len(preview_urls) == 1:
        result_dict["previewUrl"] = preview_urls[0]
    
    if is_string:
        return json.dumps(result_dict, ensure_ascii=False)
    return result_dict


def has_media_result(result: Any) -> bool:
    """
    判断任务 result 是否包含可展示的媒体结果
    
    用于 list_tasks 过滤无媒体结果的任务
    """
    urls = _extract_all_media_urls_from_result(result)
    return len(urls) > 0
