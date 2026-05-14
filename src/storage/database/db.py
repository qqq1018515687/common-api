import os
import time
import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
import logging
logger = logging.getLogger(__name__)


def to_epoch_ms(dt: datetime.datetime) -> int:
    """将 datetime 安全转为 13 位毫秒时间戳。

    修复时区偏移问题：
    - PostgreSQL TIMESTAMPTZ 列在 Asia/Shanghai 时区下，
      psycopg2 返回的是 +08:00 本地时间但 tzinfo=None (naive datetime)。
    - 如果直接 .timestamp()，Python 会按系统时区(UTC)解释，
      导致 +08 时间被当成 UTC，结果偏大 8 小时。
    - 修复：naive datetime 统一视为 UTC，确保时间戳正确。
    """
    if dt.tzinfo is None:
        # naive datetime: 视为 UTC，避免系统时区干扰
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000)

MAX_RETRY_TIME = 20  # 连接最大重试时间（秒）
# Load environment variables from .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

def get_db_url() -> str:
    """Build database URL from environment."""
    url = os.getenv("PGDATABASE_URL") or ""
    if url is not None and url != "":
        return url
    from coze_workload_identity import Client
    try:
        client = Client()
        env_vars = client.get_project_env_vars()
        client.close()
        for env_var in env_vars:
            if env_var.key == "PGDATABASE_URL":
                url = env_var.value.replace("'", "'\\''")
                return url
    except Exception as e:
        logger.error(f"Error loading PGDATABASE_URL: {e}")
        raise e
    finally:
        if url is None or url == "":
            logger.error("PGDATABASE_URL is not set")
    return url
_engine = None
_SessionLocal = None

def _create_engine_with_retry():
    url = get_db_url()
    if url is None or url == "":
        logger.error("PGDATABASE_URL is not set")
        raise ValueError("PGDATABASE_URL is not set")
    size = 100
    overflow = 100
    recycle = 1800
    timeout = 30
    engine = create_engine(
        url,
        pool_size=size,
        max_overflow=overflow,
        pool_pre_ping=True,
        pool_recycle=recycle,
        pool_timeout=timeout,
    )
    # 验证连接，带重试
    start_time = time.time()
    last_error = None
    while time.time() - start_time < MAX_RETRY_TIME:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine
        except OperationalError as e:
            last_error = e
            elapsed = time.time() - start_time
            logger.warning(f"Database connection failed, retrying... (elapsed: {elapsed:.1f}s)")
            time.sleep(min(1, MAX_RETRY_TIME - elapsed))
    logger.error(f"Database connection failed after {MAX_RETRY_TIME}s: {last_error}")
    raise last_error

def get_engine():
    global _engine
    if _engine is None:
        _engine = _create_engine_with_retry()
    return _engine

def get_sessionmaker():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal

def get_session():
    return get_sessionmaker()()

__all__ = [
    "get_db_url",
    "get_engine",
    "get_sessionmaker",
    "get_session",
]
