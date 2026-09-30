"""Private image storage and revocable, anonymous comparison viewing."""

import hashlib
import hmac
import io
import logging
import re
import secrets
import time
from urllib.parse import urlsplit, urlunsplit

import requests
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy import text

from storage.database.db import get_engine
from storage.storage_manager import get_storage_manager
from utils.backend_auth import require_backend_authorization


router = APIRouter(prefix='/api/image-comparisons', tags=['image-comparisons'])
logger = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 100_000_000
TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9_-]{32}$')
IMAGE_FORMATS = {'JPEG': ('image/jpeg', '.jpg'), 'PNG': ('image/png', '.png'), 'WEBP': ('image/webp', '.webp')}
NO_STORE = {'Cache-Control': 'private, no-store', 'X-Robots-Tag': 'noindex, nofollow'}


def authenticated_actor(authorization: str | None, actor: str | None, actor_time: str | None,
                        actor_signature: str | None) -> str:
    """Accept an identity only when the website signed it after session verification."""
    require_backend_authorization(authorization)
    if not actor or len(actor) > 64 or not actor_time or not actor_signature:
        raise HTTPException(401, 'Missing authenticated comparison actor')
    try:
        timestamp = int(actor_time)
    except ValueError as exc:
        raise HTTPException(401, 'Invalid comparison actor') from exc
    if abs(int(time.time()) - timestamp) > 300:
        raise HTTPException(401, 'Comparison actor assertion expired')
    secret = authorization.removeprefix('Bearer ')
    expected = hmac.new(secret.encode(), f'image-comparison:{actor}:{actor_time}'.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, actor_signature):
        raise HTTPException(401, 'Invalid comparison actor signature')
    return actor


def validate_image(upload: UploadFile, content: bytes) -> tuple[str, str]:
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(413, '每张图片必须小于 20MB')
    try:
        with Image.open(io.BytesIO(content)) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(400, '图片内容无效') from exc
    if image_format not in IMAGE_FORMATS or width * height > MAX_IMAGE_PIXELS:
        raise HTTPException(400, '仅支持 JPG、PNG、WebP，且图片不能超过一亿像素')
    mime, suffix = IMAGE_FORMATS[image_format]
    if upload.content_type not in (mime, 'application/octet-stream'):
        raise HTTPException(400, '图片格式与文件内容不一致')
    return mime, suffix


def validate_token(token: str) -> str:
    if not TOKEN_PATTERN.fullmatch(token):
        raise HTTPException(404, '分享不存在或已撤销')
    return token


def active_share(token: str) -> dict:
    with get_engine().connect() as conn:
        row = conn.execute(text('''SELECT s.token,s.title,s.description,s.before_object_key,s.after_object_key,
            s.before_mime_type,s.after_mime_type,s.created_at FROM image_comparison_shares s
            JOIN users u ON u.user_id=s.owner_user_id AND u.account_status='active'
            WHERE s.token=:token AND s.revoked_at IS NULL'''), {'token': validate_token(token)}).mappings().first()
    if not row:
        raise HTTPException(404, '分享不存在或已撤销')
    return dict(row)


@router.post('')
async def create_comparison(
    title: str = Form('图片对比'),
    description: str = Form(''),
    before: UploadFile = File(...),
    after: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    x_comparison_actor: str | None = Header(default=None),
    x_comparison_actor_time: str | None = Header(default=None),
    x_comparison_actor_signature: str | None = Header(default=None),
):
    user_id = authenticated_actor(authorization, x_comparison_actor, x_comparison_actor_time,
                                  x_comparison_actor_signature)
    title, description = title.strip(), description.strip()
    if not title or len(title) > 160 or len(description) > 1000:
        raise HTTPException(400, '标题或说明长度无效')
    with get_engine().connect() as conn:
        active = conn.execute(text("SELECT 1 FROM users WHERE user_id=:user AND account_status='active'"), {'user': user_id}).first()
    if not active:
        raise HTTPException(403, '账号不可用')

    before_content = await before.read(MAX_IMAGE_BYTES + 1)
    after_content = await after.read(MAX_IMAGE_BYTES + 1)
    before_mime, before_suffix = validate_image(before, before_content)
    after_mime, after_suffix = validate_image(after, after_content)
    token = secrets.token_urlsafe(24)
    prefix = f'image-comparisons-private/{hashlib.sha256(user_id.encode()).hexdigest()[:24]}/{token}'
    before_key, after_key = f'{prefix}/before{before_suffix}', f'{prefix}/after{after_suffix}'
    storage = get_storage_manager().storage
    client = storage._get_client()
    bucket = storage._resolve_bucket(None)
    uploaded = []
    try:
        for key, content, mime in ((before_key, before_content, before_mime), (after_key, after_content, after_mime)):
            client.put_object(Bucket=bucket, Key=key, Body=content, ContentType=mime, ACL='private', Metadata={
                'category': 'image_comparison_private', 'expires_in': '0', 'is_permanent': 'True',
            })
            uploaded.append(key)
            signed = urlsplit(storage.generate_presigned_url(key=key, expire_time=60))
            unsigned = urlunsplit((signed.scheme, signed.netloc, signed.path, '', ''))
            probe = requests.head(unsigned, allow_redirects=False, timeout=20)
            if probe.status_code not in (401, 403, 404):
                raise HTTPException(503, '对象存储私有访问校验未通过，请检查桶策略')
        created_at = int(time.time() * 1000)
        with get_engine().begin() as conn:
            conn.execute(text('''INSERT INTO image_comparison_shares
                (token,owner_user_id,title,description,before_object_key,after_object_key,
                 before_mime_type,after_mime_type,created_at)
                VALUES (:token,:user,:title,:description,:before_key,:after_key,:before_mime,:after_mime,:created_at)'''), {
                'token': token, 'user': user_id, 'title': title, 'description': description,
                'before_key': before_key, 'after_key': after_key,
                'before_mime': before_mime, 'after_mime': after_mime, 'created_at': created_at,
            })
    except Exception:
        for key in uploaded:
            try:
                client.delete_object(Bucket=bucket, Key=key)
            except Exception:
                logger.exception('Comparison upload rollback failed for %s', key)
        logger.exception('Comparison creation failed')
        raise
    logger.info('Image comparison created owner=%s token_suffix=%s', user_id, token[-6:])
    return {'token': token, 'title': title, 'description': description, 'createdAt': created_at}


@router.get('')
def list_comparisons(
    authorization: str | None = Header(default=None),
    x_comparison_actor: str | None = Header(default=None),
    x_comparison_actor_time: str | None = Header(default=None),
    x_comparison_actor_signature: str | None = Header(default=None),
):
    user_id = authenticated_actor(authorization, x_comparison_actor, x_comparison_actor_time,
                                  x_comparison_actor_signature)
    with get_engine().connect() as conn:
        rows = conn.execute(text('''SELECT token,title,description,created_at,revoked_at
            FROM image_comparison_shares WHERE owner_user_id=:user
            ORDER BY created_at DESC LIMIT 50'''), {'user': user_id}).mappings()
        shares = [dict(row) for row in rows]
    return {'shares': [{'token': row['token'], 'title': row['title'], 'description': row['description'],
        'createdAt': row['created_at'], 'revokedAt': row['revoked_at']} for row in shares]}


@router.get('/{token}')
def get_comparison(token: str, authorization: str | None = Header(default=None)):
    require_backend_authorization(authorization)
    share = active_share(token)
    return {'token': share['token'], 'title': share['title'], 'description': share['description'],
        'createdAt': share['created_at']}


@router.get('/{token}/images/{side}')
def get_comparison_image(token: str, side: str, authorization: str | None = Header(default=None)):
    require_backend_authorization(authorization)
    if side not in ('before', 'after'):
        raise HTTPException(404, '图片不存在')
    share = active_share(token)
    storage = get_storage_manager().storage
    try:
        object_response = storage._get_client().get_object(
            Bucket=storage._resolve_bucket(None), Key=share[f'{side}_object_key'])
    except Exception as exc:
        logger.exception('Comparison image unavailable token_suffix=%s side=%s', token[-6:], side)
        raise HTTPException(502, '图片暂不可用') from exc
    body = object_response['Body']

    def chunks():
        try:
            while part := body.read(128 * 1024):
                yield part
        finally:
            body.close()

    return StreamingResponse(chunks(), media_type=share[f'{side}_mime_type'], headers=NO_STORE)


@router.delete('/{token}')
def revoke_comparison(
    token: str,
    authorization: str | None = Header(default=None),
    x_comparison_actor: str | None = Header(default=None),
    x_comparison_actor_time: str | None = Header(default=None),
    x_comparison_actor_signature: str | None = Header(default=None),
):
    user_id = authenticated_actor(authorization, x_comparison_actor, x_comparison_actor_time,
                                  x_comparison_actor_signature)
    validate_token(token)
    now = int(time.time() * 1000)
    with get_engine().begin() as conn:
        row = conn.execute(text('''UPDATE image_comparison_shares SET revoked_at=:now
            WHERE token=:token AND owner_user_id=:user AND revoked_at IS NULL
            RETURNING before_object_key,after_object_key'''),
            {'token': token, 'user': user_id, 'now': now}).mappings().first()
        if not row:
            old = conn.execute(text('''SELECT revoked_at FROM image_comparison_shares
                WHERE token=:token AND owner_user_id=:user'''),
                {'token': token, 'user': user_id}).mappings().first()
            if not old:
                raise HTTPException(404, '分享不存在或无权撤销')
            return {'revokedAt': old['revoked_at']}
    storage = get_storage_manager().storage
    for key in (row['before_object_key'], row['after_object_key']):
        try:
            storage._get_client().delete_object(Bucket=storage._resolve_bucket(None), Key=key)
        except Exception:
            logger.exception('Revoked comparison object cleanup failed for %s', key)
    logger.info('Image comparison revoked owner=%s token_suffix=%s', user_id, token[-6:])
    return {'revokedAt': now}
