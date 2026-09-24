"""Collapse legacy operation/result pairs into image-first canvas cards.

The document remains schemaVersion 1. Historical revisions stay available for
review; restoring one is normalized by the website's existing reconciliation.
Downgrade cannot safely split user-edited cards back into two nodes.
"""
import copy
import json
import time
import uuid

from alembic import op
from sqlalchemy import text

revision = 'canvas005'
down_revision = 'canvas004'
branch_labels = None
depends_on = None


def collapse_pair(document, operation_id, asset_id, legacy_id, *, run_id=None, task_id=None):
    operation = next((n for n in document['nodes'] if n['id'] == operation_id and n['type'] == 'operation'), None)
    legacy = next((n for n in document['nodes'] if n['id'] == legacy_id and n['type'] == 'asset' and n['data'].get('assetId') == asset_id), None)
    if not operation or not legacy:
        return False
    sources = [e['source'] for e in document['edges'] if e['target'] == operation_id]
    operation['type'] = 'asset'
    operation['position'] = legacy['position']
    operation['style'] = legacy.get('style') or operation.get('style') or {'width': 260, 'height': 240}
    if legacy.get('parentId'):
        operation['parentId'] = legacy['parentId']
    operation['data'] = {**operation['data'], **legacy['data'], 'assetId': asset_id}
    if run_id:
        operation['data']['runId'] = run_id
    if task_id:
        operation['data']['sourceTaskId'] = task_id
        operation['data']['sourceImageIndex'] = 0
    document['nodes'] = [n for n in document['nodes'] if n['id'] != legacy_id]
    edges = []
    for edge in document['edges']:
        if edge['source'] == operation_id and edge['target'] == legacy_id:
            continue
        updated = dict(edge)
        if updated['source'] == legacy_id:
            updated['source'] = operation_id
        if updated['target'] == legacy_id:
            updated['target'] = operation_id
        if updated['source'] != updated['target']:
            edges.append(updated)
    # Older multi-output documents used operation -> output edges. Keep each
    # output as a sibling of the converted first result.
    for edge in list(edges):
        if edge['source'] != operation_id or edge['target'] == legacy_id:
            continue
        target = next((n for n in document['nodes'] if n['id'] == edge['target'] and n['type'] == 'asset'), None)
        if not target or not (run_id and target['data'].get('runId') == run_id or task_id and target['data'].get('sourceTaskId') == task_id):
            continue
        edges.remove(edge)
        for source in sources:
            if not any(e['source'] == source and e['target'] == target['id'] for e in edges):
                edges.append({'id': str(uuid.uuid5(uuid.NAMESPACE_URL, source + ':' + target['id'])), 'source': source, 'target': target['id']})
    document['edges'] = edges
    return True


def upgrade():
    conn = op.get_bind()
    now = int(time.time() * 1000)
    projects = conn.execute(text('SELECT id,user_id,revision,document FROM canvas_projects ORDER BY id FOR UPDATE')).mappings()
    for project in projects:
        document = copy.deepcopy(project['document'])
        changed = False
        runs = conn.execute(text("SELECT id,node_id,result FROM canvas_runs WHERE project_id=:project AND status='completed' ORDER BY created_at DESC"), {'project': project['id']}).mappings()
        for run in runs:
            asset_ids = (run['result'] or {}).get('assetIds', [])
            if not isinstance(asset_ids, list) or not asset_ids:
                continue
            legacy_id = f"result-{run['id']}-0"
            if collapse_pair(document, run['node_id'], asset_ids[0], legacy_id, run_id=run['id']):
                changed = True
        imports = conn.execute(text('''SELECT i.task_id,i.asset_id,t.parameter_snapshot FROM canvas_result_imports i
            JOIN tasks t ON t.id=i.task_id AND t.user_id=:user
            WHERE i.project_id=:project AND i.image_index=0'''), {'project': project['id'], 'user': project['user_id']}).mappings()
        for item in imports:
            snapshot = item['parameter_snapshot'] if isinstance(item['parameter_snapshot'], dict) else {}
            target = snapshot.get('canvasTarget')
            if not isinstance(target, dict) or target.get('projectId') != project['id'] or not target.get('sourceNodeId'):
                continue
            legacy_id = str(uuid.uuid5(uuid.NAMESPACE_URL, project['id'] + ':' + item['task_id'] + ':0'))
            if collapse_pair(document, target['sourceNodeId'], item['asset_id'], legacy_id, task_id=item['task_id']):
                changed = True
        if not changed:
            continue
        next_revision = project['revision'] + 1
        values = {'id': project['id'], 'revision': next_revision, 'document': json.dumps(document), 'now': now,
                  'mutation': 'canvas005:' + project['id']}
        conn.execute(text('UPDATE canvas_projects SET document=CAST(:document AS jsonb),revision=:revision,updated_at=:now WHERE id=:id'), values)
        conn.execute(text('INSERT INTO canvas_revisions (project_id,revision,mutation_id,document,created_at) VALUES (:id,:revision,:mutation,CAST(:document AS jsonb),:now)'), values)


def downgrade():
    raise RuntimeError('Image-first cards may contain later user edits. Export canvas projects before rollback.')
