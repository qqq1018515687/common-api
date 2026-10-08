"""Database-backed delivery of opted-in image tasks to canvas documents."""
import json
import logging
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import text

from storage.database.canvas_document import validate_document

logger = logging.getLogger(__name__)
SOURCE_FINGERPRINT_SQL = "md5(jsonb_build_object('result',t.result::jsonb,'fallback',t.result_fallback::jsonb,'deleted',t.deleted_image_urls::jsonb)::text)"


def _asset(conn, asset_id, user_id):
    row = conn.execute(text('SELECT id,mime_type FROM canvas_assets WHERE id=:id AND user_id=:user'), {'id': asset_id, 'user': user_id}).mappings().first()
    if not row or not row['mime_type'].startswith('image/'):
        raise HTTPException(400, '导入结果必须是当前用户的图片素材')
    return dict(row)


def _version(task, asset_ids):
    snapshot = task['parameter_snapshot'] if isinstance(task['parameter_snapshot'], dict) else {}
    params = snapshot.get('workflowParams') if isinstance(snapshot.get('workflowParams'), dict) else {}
    input_data = task['workflow_parameters'] if isinstance(task['workflow_parameters'], dict) else {}
    fields = ('aspect_ratio', 'resolution', 'size', 'width', 'height', 'quality', 'dpi', 'seed', 'steps', 'guidance', 'strength', 'noise', 'scale', 'magnify', 'upscale', 'upscale_factor', 'ratio', 'output_format', 'number', 'left', 'right', 'top', 'bottom')
    parameters = {key: value for key in fields if isinstance((value := params.get(key, input_data.get(key))), (str, int, float)) and not isinstance(value, bool) and not str(value).startswith(('http:', 'https:', 'data:', 'blob:'))}
    try:
        created_at = int(task['created_at'])
    except (TypeError, ValueError):
        created_at = 0
    version = {'id': task['id'], 'assetIds': asset_ids, 'createdAt': created_at}
    for field, value in (('model', params.get('model_name') or input_data.get('model_name')), ('modelName', snapshot.get('modelDisplayLabel') or snapshot.get('modelDisplayName') or snapshot.get('modelName')), ('workflowId', snapshot.get('workflowId')), ('prompt', params.get('prompt'))):
        if isinstance(value, str) and value and not value.startswith(('http:', 'https:', 'data:', 'blob:')):
            version[field] = value[:10000] if field == 'prompt' else value[:255]
    if parameters:
        version['parameters'] = parameters
    pricing = snapshot.get('pricingSnapshot') if isinstance(snapshot.get('pricingSnapshot'), dict) else {}
    amount = pricing.get('finalAmount')
    if isinstance(amount, (int, float)) and not isinstance(amount, bool) and 0 <= amount < 100000000:
        version['amount'] = amount
        version['currency'] = '金豆' if pricing.get('mode') == 'gold' else '银豆'
    return version


def _dispatch(conn, now):
    conn.execute(text(f"""INSERT INTO canvas_import_jobs
        (task_id,project_id,user_id,status,attempts,next_attempt_at,source_fingerprint,created_at,updated_at)
        SELECT t.id,p.id,t.user_id,'pending',0,:now,{SOURCE_FINGERPRINT_SQL},:now,:now
        FROM tasks t JOIN canvas_projects p ON p.id=t.parameter_snapshot::jsonb->'canvasTarget'->>'projectId' AND p.user_id=t.user_id AND p.status='active'
        JOIN users u ON u.user_id=t.user_id AND u.account_status='active'
        LEFT JOIN canvas_import_jobs j ON j.task_id=t.id
        WHERE t.status IN ('success','completed') AND t.type='image' AND t.platform<>'canvas'
          AND COALESCE(t.is_deleted,false)=false AND (t.result IS NOT NULL OR t.result_fallback IS NOT NULL)
          AND t.parameter_snapshot::jsonb ? 'canvasTarget' AND j.task_id IS NULL
        ON CONFLICT (task_id) DO NOTHING"""), {'now': now})
    # A task can acquire additional saved outputs after first reaching success.
    conn.execute(text(f"""UPDATE canvas_import_jobs j SET status='pending',next_attempt_at=:now,updated_at=:now
        FROM tasks t WHERE t.id=j.task_id AND j.status='completed' AND j.source_fingerprint IS DISTINCT FROM {SOURCE_FINGERPRINT_SQL}
          AND t.status IN ('success','completed') AND COALESCE(t.is_deleted,false)=false"""), {'now': now})
    rows = conn.execute(text("""SELECT j.task_id,j.project_id,j.user_id,j.status FROM canvas_import_jobs j
        JOIN users u ON u.user_id=j.user_id AND u.account_status='active'
        JOIN canvas_projects p ON p.id=j.project_id AND p.status='active'
        WHERE j.next_attempt_at<=:now AND (j.status='pending' OR (j.status='processing' AND j.lease_until<:now))
        ORDER BY j.next_attempt_at LIMIT 100"""), {'now': now}).mappings()
    return {'jobs': [dict(row) for row in rows]}


def _claim(conn, user, payload, now):
    job = conn.execute(text('SELECT * FROM canvas_import_jobs WHERE task_id=:task AND user_id=:user FOR UPDATE'), {'task': payload.get('taskId'), 'user': user}).mappings().first()
    if not job:
        raise HTTPException(404, '导入任务不存在')
    if job['status'] not in ('pending', 'processing') or job['next_attempt_at'] > now or job['status'] == 'processing' and (job['lease_until'] or 0) >= now:
        return {'claimed': False}
    task = conn.execute(text(f"""SELECT t.id,t.user_id,t.status,t.is_deleted,t.result,t.result_fallback,t.deleted_image_urls,t.parameter_snapshot,t.workflow_parameters,t.created_at,t.updated_at,
        {SOURCE_FINGERPRINT_SQL} AS source_fingerprint FROM tasks t WHERE t.id=:task AND t.user_id=:user"""), {'task': job['task_id'], 'user': user}).mappings().first()
    if task and task['is_deleted']:
        conn.execute(text("UPDATE canvas_import_jobs SET status='skipped',last_error='来源任务已删除',updated_at=:now WHERE task_id=:task"), {'now': now, 'task': job['task_id']})
        return {'claimed': False}
    if not task or task['status'] not in ('success', 'completed'):
        conn.execute(text("UPDATE canvas_import_jobs SET status='skipped',last_error='来源任务不再是成功状态',updated_at=:now WHERE task_id=:task"), {'now': now, 'task': job['task_id']})
        return {'claimed': False}
    token = str(uuid.uuid4())
    conn.execute(text("""UPDATE canvas_import_jobs SET status='processing',lease_token=:token,lease_until=:until,
        updated_at=:now WHERE task_id=:task"""), {'token': token, 'until': now + 10 * 60 * 1000, 'now': now, 'task': job['task_id']})
    receipts = [dict(row) for row in conn.execute(text('''SELECT i.image_index,i.asset_id,a.sha256 FROM canvas_result_imports i
        JOIN canvas_assets a ON a.id=i.asset_id AND a.user_id=:user
        WHERE i.project_id=:project AND i.task_id=:task'''), {'project': job['project_id'], 'task': job['task_id'], 'user': user}).mappings()]
    return {'claimed': True, 'leaseToken': token, 'sourceFingerprint': task['source_fingerprint'], 'job': {'taskId': job['task_id'], 'projectId': job['project_id'], 'userId': user},
            'result': task['result'], 'resultFallback': task['result_fallback'], 'deletedImageUrls': task['deleted_image_urls'], 'imports': receipts}


def _heartbeat(conn, user, payload, now):
    updated = conn.execute(text("""UPDATE canvas_import_jobs SET lease_until=:until,updated_at=:now
        WHERE task_id=:task AND user_id=:user AND status='processing' AND lease_token=:token AND lease_until>=:now"""),
        {'until': now + 10 * 60 * 1000, 'now': now, 'task': payload.get('taskId'), 'user': user, 'token': payload.get('leaseToken')})
    return {'accepted': updated.rowcount == 1}


def _complete(conn, user, payload, now):
    job = conn.execute(text('SELECT * FROM canvas_import_jobs WHERE task_id=:task AND user_id=:user FOR UPDATE'), {'task': payload.get('taskId'), 'user': user}).mappings().first()
    if not job or job['status'] != 'processing' or job['lease_token'] != payload.get('leaseToken') or (job['lease_until'] or 0) < now:
        raise HTTPException(409, '导入任务处理权已过期')
    task = conn.execute(text(f"""SELECT t.id,t.status,t.is_deleted,t.parameter_snapshot,t.workflow_parameters,t.created_at,t.updated_at,
        {SOURCE_FINGERPRINT_SQL} AS source_fingerprint FROM tasks t WHERE t.id=:task AND t.user_id=:user FOR UPDATE"""), {'task': job['task_id'], 'user': user}).mappings().first()
    if task and task['is_deleted']:
        conn.execute(text("UPDATE canvas_import_jobs SET status='skipped',last_error='来源任务已删除',lease_token=NULL,lease_until=NULL,updated_at=:now WHERE task_id=:task"), {'now': now, 'task': job['task_id']})
        return {'status': 'skipped'}
    if not task or task['status'] not in ('success', 'completed'):
        conn.execute(text("UPDATE canvas_import_jobs SET status='skipped',last_error='来源任务状态已变化',lease_token=NULL,lease_until=NULL,updated_at=:now WHERE task_id=:task"), {'now': now, 'task': job['task_id']})
        return {'status': 'skipped'}
    if task['source_fingerprint'] != payload.get('sourceFingerprint'):
        raise HTTPException(409, '生成结果已更新，请重新领取后导入')
    target = (task['parameter_snapshot'] or {}).get('canvasTarget') if isinstance(task['parameter_snapshot'], dict) else None
    if not isinstance(target, dict) or target.get('projectId') != job['project_id']:
        conn.execute(text("UPDATE canvas_import_jobs SET status='skipped',last_error='来源任务的画布选择已变化',lease_token=NULL,lease_until=NULL,updated_at=:now WHERE task_id=:task"), {'now': now, 'task': job['task_id']})
        return {'status': 'skipped'}
    project = conn.execute(text('SELECT * FROM canvas_projects WHERE id=:id AND user_id=:user FOR UPDATE'), {'id': job['project_id'], 'user': user}).mappings().first()
    if not project or project['status'] != 'active':
        raise HTTPException(409, '目标画布暂不可编辑')
    ids = payload.get('assetIds')
    if not isinstance(ids, list) or not 0 < len(ids) <= 100 or any(not isinstance(asset_id, str) for asset_id in ids):
        raise HTTPException(400, '没有可用图片素材')
    assets = [_asset(conn, asset_id, user) for asset_id in ids]
    receipts = {row['image_index']: row['asset_id'] for row in conn.execute(text('SELECT image_index,asset_id FROM canvas_result_imports WHERE project_id=:project AND task_id=:task'), {'project': job['project_id'], 'task': job['task_id']}).mappings()}
    imported_ids = set(receipts.values())
    document = json.loads(json.dumps(project['document']))
    source_id = target.get('sourceNodeId')
    if source_id is not None and (not isinstance(source_id, str) or not 0 < len(source_id) <= 64):
        raise HTTPException(400, '目标卡片无效')
    node = next((item for item in document['nodes'] if item['id'] == source_id), None) if source_id else next((item for item in document['nodes'] if item.get('data', {}).get('sourceTaskId') == task['id']), None)
    if (receipts and not node) or (source_id and (not node or node['type'] not in ('asset', 'operation'))):
        conn.execute(text("UPDATE canvas_import_jobs SET status='skipped',last_error='目标卡片已移除',lease_token=NULL,lease_until=NULL,updated_at=:now WHERE task_id=:task"), {'now': now, 'task': job['task_id']})
        return {'status': 'skipped'}
    old_version = next((item for item in ((node or {}).get('data', {}).get('versions') or []) if isinstance(item, dict) and item.get('id') == task['id']), None)
    if old_version and all(asset_id in imported_ids and asset_id in old_version.get('assetIds', []) for asset_id in ids):
        conn.execute(text("""UPDATE canvas_import_jobs SET status='completed',source_fingerprint=:source_fingerprint,
            last_error=NULL,lease_token=NULL,lease_until=NULL,updated_at=:now WHERE task_id=:task"""), {'source_fingerprint': task['source_fingerprint'], 'now': now, 'task': task['id']})
        return {'status': 'completed'}
    version = _version(task, ids)
    if node:
        data = node['data']
        versions = data.get('versions') if isinstance(data.get('versions'), list) else []
        existing = next((item for item in versions if isinstance(item, dict) and item.get('id') == task['id']), None)
        newest = max((item.get('createdAt', 0) for item in versions if isinstance(item, dict) and isinstance(item.get('createdAt'), (int, float))), default=0)
        if existing:
            existing.update({**version, 'assetIds': list(dict.fromkeys([*existing.get('assetIds', []), *ids]))})
        else:
            versions.append(version)
        versions.sort(key=lambda item: item.get('createdAt', 0))
        data['versions'] = versions
        if (not existing and version['createdAt'] >= newest) or not data.get('assetId'):
            data.update({'assetId': ids[0], 'mimeType': assets[0]['mime_type'], 'sourceTaskId': task['id'], 'sourceImageIndex': 0, 'selectedVersionId': task['id']})
            node['type'] = 'asset'
    else:
        node_id = str(uuid.uuid5(uuid.NAMESPACE_URL, job['project_id'] + ':' + task['id'] + ':0'))
        right = max((float(item['position']['x']) + float(item.get('style', {}).get('width', 260)) for item in document['nodes'] if not item.get('parentId')), default=-280)
        document['nodes'].append({'id': node_id, 'type': 'asset', 'position': {'x': right + 40, 'y': 80}, 'style': {'width': 260, 'height': 240},
            'data': {'label': str((task['parameter_snapshot'] or {}).get('workflowName') or '生成结果')[:160], 'assetId': ids[0], 'mimeType': assets[0]['mime_type'], 'sourceTaskId': task['id'], 'sourceImageIndex': 0, 'versions': [version], 'selectedVersionId': task['id']}})
    validate_document(document)
    revision = project['revision'] + 1
    values = {'project': job['project_id'], 'task': task['id'], 'revision': revision, 'now': now, 'document': json.dumps(document), 'mutation': 'auto-import:' + task['id'] + ':' + str(revision)}
    conn.execute(text('UPDATE canvas_projects SET document=CAST(:document AS jsonb),revision=:revision,updated_at=:now WHERE id=:project'), values)
    conn.execute(text('INSERT INTO canvas_revisions (project_id,revision,mutation_id,document,created_at) VALUES (:project,:revision,:mutation,CAST(:document AS jsonb),:now)'), values)
    next_index = max(receipts, default=-1) + 1
    for asset_id in ids:
        if asset_id not in imported_ids:
            conn.execute(text('INSERT INTO canvas_result_imports (project_id,task_id,image_index,asset_id,created_at) VALUES (:project,:task,:index,:asset,:now)'), {'project': job['project_id'], 'task': task['id'], 'index': next_index, 'asset': asset_id, 'now': now})
            imported_ids.add(asset_id)
            next_index += 1
    conn.execute(text("""UPDATE canvas_import_jobs SET status='completed',source_fingerprint=:source_fingerprint,
        last_error=NULL,lease_token=NULL,lease_until=NULL,updated_at=:now WHERE task_id=:task"""), {'source_fingerprint': task['source_fingerprint'], 'now': now, 'task': task['id']})
    logger.info('[Canvas] imported task=%s project=%s outputs=%s', task['id'], job['project_id'], len(ids))
    return {'status': 'completed'}


def _fail(conn, user, payload, now):
    job = conn.execute(text('SELECT * FROM canvas_import_jobs WHERE task_id=:task AND user_id=:user FOR UPDATE'), {'task': payload.get('taskId'), 'user': user}).mappings().first()
    if not job or job['status'] != 'processing' or job['lease_token'] != payload.get('leaseToken'):
        return {'accepted': False}
    attempts = job['attempts'] + 1
    delay = min(3600000, 30000 * 2 ** min(attempts, 7))
    conn.execute(text("""UPDATE canvas_import_jobs SET status='pending',attempts=:attempts,next_attempt_at=:next,
        last_error=:error,lease_token=NULL,lease_until=NULL,updated_at=:now WHERE task_id=:task"""),
        {'attempts': attempts, 'next': now + delay, 'error': str(payload.get('error') or '素材暂时无法保存')[:500], 'now': now, 'task': job['task_id']})
    logger.warning('[Canvas] import retry task=%s attempt=%s', job['task_id'], attempts)
    return {'accepted': True, 'nextAttemptAt': now + delay}


def handle_import_action(conn, user, action, payload, now):
    if action == 'dispatch_imports':
        return _dispatch(conn, now)
    if action == 'claim_import':
        return _claim(conn, user, payload, now)
    if action == 'heartbeat_import':
        return _heartbeat(conn, user, payload, now)
    if action == 'complete_import':
        return _complete(conn, user, payload, now)
    if action == 'fail_import':
        return _fail(conn, user, payload, now)
    if action == 'import_status':
        rows = conn.execute(text("""SELECT task_id,project_id,status,attempts,last_error,updated_at
            FROM canvas_import_jobs WHERE user_id=:user ORDER BY created_at DESC LIMIT 100"""), {'user': user}).mappings()
        return {'serverManaged': True, 'jobs': [dict(row) for row in rows]}
    raise HTTPException(400, '不支持的导入操作')
