"""Trusted website gateway API; identity is supplied only by authenticated backend.

Every resource lookup is owner scoped. No arbitrary SQL/table names or remote URLs.
"""
import base64
import hashlib
import json
import logging
import time
import uuid
from typing import Any
from urllib.parse import urlsplit, urlunsplit
import requests

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from storage.database.db import get_engine
from storage.database.canvas_document import validate_document
from storage.storage_manager import get_storage_manager
from utils.backend_auth import require_backend_authorization

router = APIRouter(prefix='/api/canvas', tags=['canvas'])
logger = logging.getLogger(__name__)
EMPTY = {'schemaVersion': 1, 'nodes': [], 'edges': [], 'importedRunIds': [], 'viewport': {'x': 0, 'y': 0, 'zoom': 1}}


class CanvasRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    action: str
    project_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


def owned_project(conn, project_id, user_id, *, lock=False):
    row = conn.execute(text('SELECT * FROM canvas_projects WHERE id=:id AND user_id=:user' + (' FOR UPDATE' if lock else '')), {'id': project_id, 'user': user_id}).mappings().first()
    if not row:
        raise HTTPException(404, '项目不存在或无权访问')
    return dict(row)


def owned_asset(conn, asset_id, user_id):
    row = conn.execute(text('SELECT * FROM canvas_assets WHERE id=:id AND user_id=:user'), {'id': asset_id, 'user': user_id}).mappings().first()
    if not row:
        raise HTTPException(404, '素材不存在或无权访问')
    return dict(row)


def check_assets(conn, document, user_id):
    for asset_id in validate_document(document):
        owned_asset(conn, asset_id, user_id)


def insert_project(conn, project_id, user_id, title, document, now):
    check_assets(conn, document, user_id)
    conn.execute(text('INSERT INTO canvas_projects (id,user_id,title,document,created_at,updated_at) VALUES (:id,:user,:title,CAST(:doc AS jsonb),:now,:now)'), {'id': project_id, 'user': user_id, 'title': title, 'doc': json.dumps(document), 'now': now})
    conn.execute(text('INSERT INTO canvas_revisions (project_id,revision,mutation_id,document,created_at) VALUES (:id,0,:id,CAST(:doc AS jsonb),:now)'), {'id': project_id, 'doc': json.dumps(document), 'now': now})
    return owned_project(conn, project_id, user_id)


@router.post('')
def canvas(request: CanvasRequest, authorization: str | None = Header(default=None)):
    require_backend_authorization(authorization)
    now = int(time.time() * 1000)
    user, action, p = request.user_id, request.action, request.payload
    try:
        with get_engine().begin() as conn:
            if action == 'dispatch_runs':
                # Internal backend token only; the website allowlist never exposes this.
                rows = conn.execute(text("""SELECT r.id,r.user_id,r.project_id,r.status FROM canvas_runs r
                    JOIN users u ON u.user_id=r.user_id AND u.account_status='active'
                    JOIN canvas_projects p ON p.id=r.project_id
                    WHERE r.status='queued'
                       OR (r.status='claimed' AND r.lease_until < :now)
                       OR (r.status IN ('running','unknown','asset_failed') AND r.updated_at < :cutoff)
                    ORDER BY r.updated_at LIMIT 100"""), {'now': now, 'cutoff': now - 15000}).mappings()
                return {'runs': [dict(row) for row in rows]}
            active = conn.execute(text("SELECT user_id FROM users WHERE user_id=:user AND account_status='active'"), {'user': user}).first()
            if not active:
                raise HTTPException(403, '账号不可用')
            if action == 'list':
                return {'projects': [dict(r) for r in conn.execute(text('SELECT id,title,status,revision,created_at,updated_at FROM canvas_projects WHERE user_id=:user ORDER BY updated_at DESC LIMIT 500'), {'user': user}).mappings()]}
            if action == 'create':
                project_id = str(uuid.UUID(p['id']))
                existing = conn.execute(text('SELECT id FROM canvas_projects WHERE id=:id'), {'id': project_id}).first()
                if existing:
                    return {'project': owned_project(conn, project_id, user)}
                title = str(p.get('title') or '未命名项目').strip()[:160]
                return {'project': insert_project(conn, project_id, user, title, EMPTY, now)}
            if action == 'assets':
                return {'assets': [dict(r) for r in conn.execute(text('SELECT id,file_name,mime_type,size,created_at FROM canvas_assets WHERE user_id=:user ORDER BY created_at DESC LIMIT 300'), {'user': user}).mappings()]}
            if action in ('asset', 'sign'):
                asset = owned_asset(conn, p.get('assetId'), user)
                if action == 'asset':
                    return {'asset': {k: v for k, v in asset.items() if k != 'object_key'}}
                storage = get_storage_manager().storage
                return {'asset': {k: v for k, v in asset.items() if k != 'object_key'}, 'url': storage.generate_presigned_url(key=asset['object_key'], expire_time=900), 'expiresAt': now + 900000}
            if action == 'upload':
                asset_id = str(uuid.UUID(p['id']))
                old = conn.execute(text('SELECT id FROM canvas_assets WHERE id=:id'), {'id': asset_id}).first()
                if old:
                    asset = owned_asset(conn, asset_id, user)
                    return {'asset': {k: v for k, v in asset.items() if k != 'object_key'}}
                mime = str(p.get('mimeType', ''))
                suffix = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'image/gif': '.gif', 'video/mp4': '.mp4', 'video/webm': '.webm'}.get(mime)
                if not suffix:
                    raise HTTPException(400, '仅支持常用图片和视频格式')
                raw = base64.b64decode(p['base64'], validate=True)
                signatures = {'image/png': raw.startswith(b'\x89PNG\r\n\x1a\n'), 'image/jpeg': raw.startswith(b'\xff\xd8\xff'), 'image/webp': raw[:4] == b'RIFF' and raw[8:12] == b'WEBP', 'image/gif': raw[:6] in (b'GIF87a', b'GIF89a'), 'video/mp4': raw[4:8] == b'ftyp', 'video/webm': raw[:4] == b'\x1aE\xdf\xa3'}
                if not signatures.get(mime):
                    raise HTTPException(400, '文件内容与媒体格式不一致')
                if not 0 < len(raw) <= 64 * 1024 * 1024:
                    raise HTTPException(413, '文件必须小于 64MB')
                key = f'canvas-private/{hashlib.sha256(user.encode()).hexdigest()[:24]}/{asset_id}{suffix}'
                storage = get_storage_manager().storage
                # Dedicated permanent prefix: not included in temporary/upload cleanup.
                # Bucket policy must also disallow anonymous reads; deployment probe verifies it.
                storage._get_client().put_object(Bucket=storage._resolve_bucket(None), Key=key, Body=raw, ContentType=mime, ACL='private', Metadata={'category': 'canvas_private', 'expires_in': '0', 'is_permanent': 'True'})
                signed = urlsplit(storage.generate_presigned_url(key=key, expire_time=60))
                unsigned = urlunsplit((signed.scheme, signed.netloc, signed.path, '', ''))
                probe = requests.head(unsigned, allow_redirects=False, timeout=20)
                if probe.status_code not in (401, 403, 404):
                    storage._get_client().delete_object(Bucket=storage._resolve_bucket(None), Key=key)
                    raise HTTPException(503, '对象存储私有访问校验未通过，请检查桶策略')
                asset = {'id': asset_id, 'user': user, 'key': key, 'name': str(p.get('fileName', '素材'))[:255], 'mime': mime, 'size': len(raw), 'hash': hashlib.sha256(raw).hexdigest(), 'now': now}
                conn.execute(text('INSERT INTO canvas_assets (id,user_id,object_key,file_name,mime_type,size,sha256,created_at) VALUES (:id,:user,:key,:name,:mime,:size,:hash,:now)'), asset)
                return {'asset': {k: v for k, v in owned_asset(conn, asset_id, user).items() if k != 'object_key'}}
            project = owned_project(conn, request.project_id, user, lock=True)
            if action == 'get':
                return {'project': project}
            if action in ('result_imports', 'import_result'):
                task_id = str(p.get('taskId', ''))
                if not task_id or len(task_id) > 128:
                    raise HTTPException(400, '无效来源任务')
                task = conn.execute(text('SELECT id,status,parameter_snapshot FROM tasks WHERE id=:id AND user_id=:user'), {'id': task_id, 'user': user}).mappings().first()
                if not task:
                    raise HTTPException(404, '来源任务尚未同步或无权访问')
                receipts = [dict(row) for row in conn.execute(text('SELECT image_index,asset_id FROM canvas_result_imports WHERE project_id=:project AND task_id=:task'), {'project': project['id'], 'task': task_id}).mappings()]
                if action == 'result_imports':
                    return {'imports': receipts}
                if task['status'] != 'success':
                    raise HTTPException(409, '来源任务尚未生成成功')
                index = p.get('imageIndex')
                if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < 100:
                    raise HTTPException(400, '无效图片序号')
                if any(row['image_index'] == index for row in receipts):
                    return {'project': project, 'imported': False}
                if project['status'] != 'active':
                    raise HTTPException(409, '目标画布已归档或删除，结果尚未加入')
                asset = owned_asset(conn, p.get('assetId'), user)
                if not asset['mime_type'].startswith('image/'):
                    raise HTTPException(400, '自动加入仅支持图片')
                document = project['document']
                source_id = p.get('sourceNodeId')
                if source_id is not None:
                    if not isinstance(source_id, str) or not 0 < len(source_id) <= 64:
                        raise HTTPException(400, '来源节点无效')
                    target = (task['parameter_snapshot'] or {}).get('canvasTarget') if isinstance(task['parameter_snapshot'], dict) else None
                    if not isinstance(target, dict) or target.get('projectId') != project['id'] or target.get('sourceNodeId') != source_id:
                        raise HTTPException(400, '来源任务与画布节点不匹配')
                source = next((node for node in document['nodes'] if node['id'] == source_id), None) if source_id else None
                node_id = str(uuid.uuid5(uuid.NAMESPACE_URL, project['id'] + ':' + task_id + ':' + str(index)))
                skipped = bool(source_id and not source)
                if source_id and source and source['type'] not in ('operation', 'asset'):
                    raise HTTPException(409, '来源节点已经改变，请从任务列表重新加入结果')
                if source_id and index > 0 and source and source['type'] == 'operation':
                    raise HTTPException(409, '请先导入首张结果')
                if source_id and source and source['type'] == 'asset' and source['data'].get('sourceTaskId') != task_id:
                    raise HTTPException(409, '来源节点已有其他结果')
                if not skipped and source_id and source and index == 0:
                    source['type'] = 'asset'
                    source['style'] = source.get('style') or {'width': 260, 'height': 240}
                    source['data'] = {**source['data'], 'assetId': asset['id'], 'mimeType': asset['mime_type'], 'sourceTaskId': task_id, 'sourceImageIndex': index}
                elif not skipped:
                    # Project lock makes the result card and its receipt one durable change.
                    right = max((float(n['position']['x']) + float(n.get('style', {}).get('width', 260)) for n in document['nodes'] if not n.get('parentId')), default=-280)
                    document['nodes'].append({'id': node_id, 'type': 'asset', 'position': {'x': right + 40, 'y': source['position']['y'] if source else 80}, 'style': {'width': 260, 'height': 240}, 'data': {'label': str(p.get('label') or asset['file_name'])[:160], 'assetId': asset['id'], 'mimeType': asset['mime_type'], 'sourceTaskId': task_id, 'sourceImageIndex': index}})
                    if source:
                        for edge in list(document['edges']):
                            if edge['target'] == source_id:
                                document['edges'].append({'id': str(uuid.uuid5(uuid.NAMESPACE_URL, node_id + ':' + edge['source'])), 'source': edge['source'], 'target': node_id})
                check_assets(conn, document, user)
                values = {'project': project['id'], 'task': task_id, 'index': index, 'asset': asset['id'], 'now': now, 'revision': project['revision'] + 1, 'document': json.dumps(document), 'mutation': node_id}
                conn.execute(text('UPDATE canvas_projects SET document=CAST(:document AS jsonb),revision=:revision,updated_at=:now WHERE id=:project'), values)
                conn.execute(text('INSERT INTO canvas_revisions (project_id,revision,mutation_id,document,created_at) VALUES (:project,:revision,:mutation,CAST(:document AS jsonb),:now)'), values)
                conn.execute(text('INSERT INTO canvas_result_imports (project_id,task_id,image_index,asset_id,created_at) VALUES (:project,:task,:index,:asset,:now)'), values)
                return {'project': owned_project(conn, project['id'], user), 'imported': True, 'skipped': skipped}
            if action.startswith('assistant_'):
                conn.execute(text("UPDATE canvas_assistant_turns SET status='failed',error='创作规划已超时，可重新提交',updated_at=:now WHERE project_id=:project AND status='running' AND created_at<:cutoff"), {'project': project['id'], 'now': now, 'cutoff': now - 120000})
                if action == 'assistant_history':
                    return {'turns': [dict(row) for row in conn.execute(text('SELECT * FROM canvas_assistant_turns WHERE project_id=:project AND user_id=:user ORDER BY created_at DESC LIMIT 50'), {'project': project['id'], 'user': user}).mappings()]}
                turn_id = str(uuid.UUID(p['id']))
                turn = conn.execute(text('SELECT * FROM canvas_assistant_turns WHERE id=:id AND project_id=:project AND user_id=:user FOR UPDATE'), {'id': turn_id, 'project': project['id'], 'user': user}).mappings().first()
                if action == 'assistant_start':
                    if turn:
                        return {'started': False, 'turn': dict(turn), 'project': project}
                    if project['status'] != 'active' or p.get('revision') != project['revision']:
                        raise HTTPException(409, '请先同步项目后再规划')
                    if conn.execute(text("SELECT id FROM canvas_assistant_turns WHERE project_id=:project AND status='running'"), {'project': project['id']}).first():
                        raise HTTPException(409, '此项目正在规划，请稍候')
                    # Serialize only planning reservations for this account across projects.
                    conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {'key': 'canvas-assistant:' + user})
                    recent = conn.execute(text('SELECT count(*) FROM canvas_assistant_turns WHERE user_id=:user AND created_at>:cutoff'), {'user': user, 'cutoff': now - 60000}).scalar_one()
                    if recent >= 10:
                        raise HTTPException(429, '创作规划过于频繁，请稍后重试')
                    message = str(p.get('message', '')).strip()
                    selected = p.get('selectedNodeIds', [])
                    if not message or len(message) > 4000 or not isinstance(selected, list) or len(selected) > 6:
                        raise HTTPException(400, '创作要求或选中素材无效')
                    allowed = {n['id'] for n in project['document']['nodes'] if n['type'] == 'asset'}
                    if any(node not in allowed for node in selected):
                        raise HTTPException(400, '选中素材不属于此画布')
                    conn.execute(text("INSERT INTO canvas_assistant_turns (id,project_id,user_id,revision,status,request,created_at,updated_at) VALUES (:id,:project,:user,:revision,'running',CAST(:request AS jsonb),:now,:now)"), {'id': turn_id, 'project': project['id'], 'user': user, 'revision': project['revision'], 'request': json.dumps({'message': message, 'selectedNodeIds': selected}), 'now': now})
                    return {'started': True}
                if not turn:
                    raise HTTPException(404, '创作规划不存在')
                if turn['status'] != 'running':
                    return {'turn': dict(turn), 'project': project}
                if action == 'assistant_finish':
                    response = p.get('response', {})
                    if len(json.dumps(response).encode()) > 128000:
                        raise HTTPException(400, '创作规划结果过大')
                    if project['status'] != 'active' or project['revision'] != turn['revision']:
                        conn.execute(text("UPDATE canvas_assistant_turns SET status='failed',response=CAST(:response AS jsonb),error='画布已改变，规划未应用，请重新规划',updated_at=:now WHERE id=:id"), {'id': turn_id, 'response': json.dumps(response), 'now': now})
                        return {'conflict': True}
                    document = p['document']
                    check_assets(conn, document, user)
                    document['importedRunIds'] = sorted(set(document.get('importedRunIds', [])) | set(project['document'].get('importedRunIds', [])))
                    values = {'project': project['id'], 'id': turn_id, 'revision': project['revision'] + 1, 'document': json.dumps(document), 'response': json.dumps(response), 'now': now}
                    conn.execute(text('UPDATE canvas_projects SET document=CAST(:document AS jsonb),revision=:revision,updated_at=:now WHERE id=:project'), values)
                    conn.execute(text('INSERT INTO canvas_revisions (project_id,revision,mutation_id,document,created_at) VALUES (:project,:revision,:id,CAST(:document AS jsonb),:now)'), values)
                    conn.execute(text("UPDATE canvas_assistant_turns SET status='completed',response=CAST(:response AS jsonb),updated_at=:now WHERE id=:id"), values)
                    return {'project': owned_project(conn, project['id'], user), 'response': response}
                if action == 'assistant_fail':
                    conn.execute(text("UPDATE canvas_assistant_turns SET status='failed',error=:error,updated_at=:now WHERE id=:id"), {'id': turn_id, 'error': str(p.get('error', '规划失败'))[:1000], 'now': now})
                    return {'ok': True}
                raise HTTPException(400, '无效创作规划操作')
            if action == 'abort_submission':
                key = str(uuid.UUID(p['runId']))
                old = conn.execute(text('SELECT * FROM canvas_runs WHERE id=:id AND project_id=:project AND user_id=:user'), {'id': key, 'project': project['id'], 'user': user}).mappings().first()
                if old:
                    return {'run': dict(old), 'cancelled': False}
                # Tombstone closes the race with a delayed reserve request. Never
                # delete an uncertain key locally without fencing it server-side.
                conn.execute(text("INSERT INTO canvas_runs (id,project_id,user_id,node_id,idempotency_key,request_hash,status,request,error,created_at,updated_at) VALUES (:id,:project,:user,:node,:id,'cancelled','failed','{}','提交已取消，未执行',:now,:now)"), {'id': key, 'project': project['id'], 'user': user, 'node': str(p.get('nodeId', ''))[:64], 'now': now})
                return {'run': {'id': key, 'status': 'failed'}, 'cancelled': True}
            if action == 'find_run':
                row = conn.execute(text('SELECT * FROM canvas_runs WHERE id=:id AND project_id=:project AND user_id=:user'), {'id': p.get('runId'), 'project': project['id'], 'user': user}).mappings().first()
                return {'run': dict(row) if row else None}
            if action == 'reserve_run':
                if project['status'] != 'active' or p.get('revision') != project['revision']:
                    raise HTTPException(409, '请先同步项目再执行')
                node = next((n for n in project['document']['nodes'] if n['id'] == p.get('nodeId') and n['type'] == 'operation'), None)
                if not node:
                    raise HTTPException(400, '操作节点不存在')
                snapshot = p['request']
                inputs = snapshot.get('assetIds', [])
                for asset_id in inputs:
                    if not owned_asset(conn, asset_id, user)['mime_type'].startswith('image/'):
                        raise HTTPException(400, '当前操作仅接受图片素材')
                request_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
                key = str(uuid.UUID(p['idempotencyKey']))
                old = conn.execute(text('SELECT * FROM canvas_runs WHERE user_id=:user AND idempotency_key=:key'), {'user': user, 'key': key}).mappings().first()
                if old:
                    if old['project_id'] != project['id'] or old['request_hash'] != request_hash or old['node_id'] != node['id']:
                        raise HTTPException(409, '同一提交标识不能用于不同请求')
                    return {'run': dict(old)}
                pending = conn.execute(text("SELECT * FROM canvas_runs WHERE project_id=:project AND node_id=:node AND status IN ('queued','claimed','running','unknown','asset_failed') ORDER BY created_at DESC LIMIT 1"), {'project': project['id'], 'node': node['id']}).mappings().first()
                if pending:
                    if pending['request_hash'] == request_hash:
                        return {'run': dict(pending)}
                    raise HTTPException(409, '此节点还有任务待确认，请先完成恢复或使用新的操作节点')
                run_id = key
                conn.execute(text("INSERT INTO canvas_runs (id,project_id,user_id,node_id,idempotency_key,request_hash,status,request,task_id,created_at,updated_at) VALUES (:id,:project,:user,:node,:id,:hash,'queued',CAST(:request AS jsonb),:id,:now,:now)"), {'id': run_id, 'project': project['id'], 'user': user, 'node': node['id'], 'hash': request_hash, 'request': json.dumps(snapshot), 'now': now})
                return {'run': dict(conn.execute(text('SELECT * FROM canvas_runs WHERE id=:id'), {'id': run_id}).mappings().one())}
            if action in ('claim_run', 'begin_run', 'heartbeat_run', 'touch_run', 'update_run', 'run_task'):
                run = conn.execute(text('SELECT * FROM canvas_runs WHERE id=:id AND project_id=:project AND user_id=:user FOR UPDATE'), {'id': p.get('runId'), 'project': project['id'], 'user': user}).mappings().first()
                if not run:
                    raise HTTPException(404, '执行记录不存在')
                if action == 'touch_run':
                    conn.execute(text('UPDATE canvas_runs SET updated_at=:now WHERE id=:id'), {'id': run['id'], 'now': now})
                    return {'ok': True}
                if action == 'run_task':
                    task = conn.execute(text('SELECT status,result,result_fallback,error,deduction_result FROM tasks WHERE id=:id AND user_id=:user'), {'id': run['task_id'], 'user': user}).mappings().first()
                    return {'run': dict(run), 'task': dict(task) if task else None}
                if action == 'claim_run':
                    reclaim = run['status'] == 'claimed' and (run['lease_until'] or 0) < now
                    if run['status'] != 'queued' and not reclaim:
                        return {'claimed': False, 'run': dict(run)}
                    if project['status'] != 'active':
                        conn.execute(text("UPDATE canvas_runs SET status='failed',error='项目已归档或删除，尚未执行',updated_at=:now WHERE id=:id"), {'now': now, 'id': run['id']})
                        return {'claimed': False, 'run': dict(run)}
                    urls = [get_storage_manager().storage.generate_presigned_url(key=owned_asset(conn, a, user)['object_key'], expire_time=3600) for a in run['request']['assetIds']]
                    token = str(uuid.uuid4())
                    conn.execute(text("UPDATE canvas_runs SET status='claimed',lease_token=:token,lease_until=:until,updated_at=:now WHERE id=:id"), {'token': token, 'until': now + 60000, 'now': now, 'id': run['id']})
                    return {'claimed': True, 'leaseToken': token, 'run': dict(run), 'inputUrls': urls}
                if action in ('begin_run', 'heartbeat_run'):
                    if action == 'begin_run' and project['status'] != 'active':
                        conn.execute(text("UPDATE canvas_runs SET status='failed',error='项目已归档或删除，尚未执行',updated_at=:now WHERE id=:id"), {'now': now, 'id': run['id']})
                        return {'accepted': False}
                    expected = 'claimed' if action == 'begin_run' else 'running'
                    if run['status'] != expected or run['lease_token'] != p.get('leaseToken') or (run['lease_until'] or 0) < now:
                        return {'accepted': False}
                    conn.execute(text("UPDATE canvas_runs SET status='running',started_at=COALESCE(started_at,:now),lease_until=:until,updated_at=:now WHERE id=:id"), {'id': run['id'], 'now': now, 'until': now + 120000})
                    return {'accepted': True}
                status = p.get('status')
                if status not in ('completed', 'failed', 'unknown', 'asset_failed'):
                    raise HTTPException(400, '无效执行状态')
                if run['status'] in ('completed', 'failed'):
                    return {'run': dict(run)}
                result = p.get('result')
                if result:
                    for asset_id in result.get('assetIds', []):
                        owned_asset(conn, asset_id, user)
                    if set(result) - {'assetIds', 'billing'}:
                        raise HTTPException(400, '结果只能保存资产引用与计费记录')
                conn.execute(text('UPDATE canvas_runs SET status=:status,result=CAST(:result AS jsonb),error=:error,updated_at=:now WHERE id=:id'), {'id': run['id'], 'status': status, 'result': json.dumps(result), 'error': str(p.get('error', ''))[:2000], 'now': now})
                return {'ok': True}
            if action == 'runs':
                return {'runs': [dict(r) for r in conn.execute(text('SELECT * FROM canvas_runs WHERE project_id=:id AND user_id=:user ORDER BY created_at DESC LIMIT 300'), {'id': project['id'], 'user': user}).mappings()]}
            if action == 'versions':
                return {'versions': [dict(r) for r in conn.execute(text('SELECT revision,created_at FROM canvas_revisions WHERE project_id=:id ORDER BY revision DESC LIMIT 100'), {'id': project['id']}).mappings()]}
            if action == 'version':
                row = conn.execute(text('SELECT document,revision FROM canvas_revisions WHERE project_id=:id AND revision=:rev'), {'id': project['id'], 'rev': p['revision']}).mappings().first()
                if not row:
                    raise HTTPException(404, '版本不存在')
                return dict(row)
            if action == 'copy':
                target = str(uuid.UUID(p['id']))
                existing = conn.execute(text('SELECT id FROM canvas_projects WHERE id=:id'), {'id': target}).first()
                if existing:
                    return {'project': owned_project(conn, target, user)}
                document = json.loads(json.dumps(project['document']))
                for node in document['nodes']:
                    node['data'].pop('runId', None)
                return {'project': insert_project(conn, target, user, (project['title'] + ' 副本')[:160], document, now)}
            if action in ('save', 'rename', 'archive', 'delete', 'restore'):
                mutation = str(uuid.UUID(p['mutationId']))
                applied = conn.execute(text('SELECT revision FROM canvas_revisions WHERE project_id=:id AND mutation_id=:mutation'), {'id': project['id'], 'mutation': mutation}).first()
                if applied:
                    if project['revision'] != applied[0]:
                        raise HTTPException(409, '项目在此次保存之后已有更新，请保留草稿并解决冲突')
                    return {'project': project}
                if p.get('revision') != project['revision']:
                    raise HTTPException(409, {'message': '项目已在其他设备更新，本地草稿已保留', 'project': project})
                if project['status'] != 'active' and action not in ('restore', 'delete'):
                    raise HTTPException(409, '请先恢复项目再编辑')
                document = p.get('document') if action == 'save' else project['document']
                check_assets(conn, document, user)
                document = dict(document)
                document['importedRunIds'] = sorted(set(project['document'].get('importedRunIds', [])) | set(document.get('importedRunIds', [])))
                title = str(p.get('title', '')).strip()[:160] if action == 'rename' else project['title']
                if not title:
                    raise HTTPException(400, '项目名称不能为空')
                status = {'archive': 'archived', 'delete': 'deleted', 'restore': 'active'}.get(action, project['status'])
                values = {'id': project['id'], 'title': title, 'status': status, 'doc': json.dumps(document), 'rev': project['revision'] + 1, 'now': now, 'mutation': mutation}
                conn.execute(text('UPDATE canvas_projects SET title=:title,status=:status,document=CAST(:doc AS jsonb),revision=:rev,updated_at=:now WHERE id=:id'), values)
                conn.execute(text('INSERT INTO canvas_revisions (project_id,revision,mutation_id,document,created_at) VALUES (:id,:rev,:mutation,CAST(:doc AS jsonb),:now)'), values)
                return {'project': owned_project(conn, project['id'], user)}
            raise HTTPException(400, '不支持的画布操作')
    except HTTPException:
        raise
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning('[Canvas] invalid request action=%s user=%s: %s', action, user, exc)
        raise HTTPException(400, '画布参数无效') from exc
    except Exception:
        logger.exception('[Canvas] operation failed action=%s user=%s', action, user)
        raise
