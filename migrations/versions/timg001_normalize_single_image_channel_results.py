"""normalize single-image channel results

Revision ID: timg001
Revises: taskstatus001
Create Date: 2026-09-11 16:30:00.000000
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "timg001"
down_revision: Union[str, Sequence[str], None] = "taskstatus001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_result(result: dict) -> dict:
    image_urls = result.get("imageUrls")
    if not isinstance(image_urls, list) or len(image_urls) <= 1:
        return result

    normalized = dict(result)
    for key in ("imageUrls", "files", "images", "outputs", "thumbnailUrls", "previewUrls"):
        value = normalized.get(key)
        if isinstance(value, list) and value:
            normalized[key] = [value[-1]]

    final_url = normalized["imageUrls"][0]
    for key in ("image_url", "thumbnailUrl", "previewUrl"):
        if key in normalized:
            normalized[key] = final_url

    metadata = normalized.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("localProvider"), dict):
        normalized_metadata = dict(metadata)
        local_provider = dict(metadata["localProvider"])
        for key in ("imageUrls", "commonPublicUrls"):
            value = local_provider.get(key)
            if isinstance(value, list) and value:
                local_provider[key] = [value[-1]]
        if "commonPublicUrl" in local_provider:
            local_provider["commonPublicUrl"] = final_url
        normalized_metadata["localProvider"] = local_provider
        normalized["metadata"] = normalized_metadata

    return normalized


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("""
        SELECT id, result
        FROM tasks
        WHERE platform IN ('tudou', 'local_sub2api')
          AND created_at::bigint >= 1789056000000
          AND jsonb_typeof(result::jsonb->'imageUrls') = 'array'
          AND jsonb_array_length(result::jsonb->'imageUrls') > 1
    """)).mappings()

    for row in rows:
        result = row["result"]
        if not isinstance(result, dict):
            continue
        bind.execute(
            sa.text("UPDATE tasks SET result = CAST(:result AS json) WHERE id = :task_id"),
            {
                "task_id": row["id"],
                "result": json.dumps(_normalize_result(result), ensure_ascii=False),
            },
        )


def downgrade() -> None:
    # 被供应商重复返回的预览图无法可靠恢复，数据清理不做反向回填。
    pass
