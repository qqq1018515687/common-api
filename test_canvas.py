"""Real PostgreSQL tests. Never runs against a non-loopback database."""
import copy
import base64
import importlib.util
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch, MagicMock
from urllib.parse import urlsplit
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from api import canvas as api
from storage.database.canvas_document import validate_document


class DocumentTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(validate_document(copy.deepcopy(api.EMPTY)), set())

    def test_private_reference_only(self):
        doc = copy.deepcopy(api.EMPTY)
        doc['nodes'] = [{'id': 'a', 'type': 'asset', 'position': {'x': 0, 'y': 0}, 'data': {'assetId': 'asset', 'url': 'https://private.invalid'}}]
        with self.assertRaises(ValueError):
            validate_document(doc)

    def test_cycles_and_nan(self):
        doc = copy.deepcopy(api.EMPTY)
        doc['viewport']['x'] = float('nan')
        with self.assertRaises(ValueError):
            validate_document(doc)
        doc = copy.deepcopy(api.EMPTY)
        doc['nodes'] = [{'id': 'a', 'type': 'group', 'parentId': 'a', 'position': {'x': 0, 'y': 0}, 'data': {}}]
        with self.assertRaises(ValueError):
            validate_document(doc)


@unittest.skipUnless(os.getenv('CANVAS_TEST_DATABASE_URL'), 'requires isolated local PostgreSQL')
class CanvasDatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.environ['CANVAS_TEST_DATABASE_URL']
        if urlsplit(url.replace('postgresql+psycopg2', 'postgresql')).hostname not in ('127.0.0.1', 'localhost'):
            raise RuntimeError('Refusing non-local test database')
        cls.schema = 'canvas_test_' + uuid.uuid4().hex
        cls.base = create_engine(url)
        with cls.base.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA {cls.schema}'))
        cls.engine = create_engine(url, connect_args={'options': f'-csearch_path={cls.schema}'})
        with cls.engine.begin() as conn:
            conn.execute(text('CREATE TABLE users (user_id varchar(64) PRIMARY KEY, account_status varchar(20))'))
            conn.execute(text("INSERT INTO users VALUES ('alice','active'),('bob','active'),('blocked','disabled')"))
            conn.execute(text('CREATE TABLE tasks (id varchar(64),user_id varchar(64),status text,result jsonb,result_fallback jsonb,error text,deduction_result jsonb)'))
            spec = importlib.util.spec_from_file_location('canvas_migration', Path(__file__).parent / 'migrations/versions/canvas001_creative_canvas.py')
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
            spec = importlib.util.spec_from_file_location('canvas_lease_migration', Path(__file__).parent / 'migrations/versions/canvas002_execution_leases.py')
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
            spec = importlib.util.spec_from_file_location('canvas_assistant_migration', Path(__file__).parent / 'migrations/versions/canvas003_assistant_turns.py')
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()

            spec = importlib.util.spec_from_file_location('canvas_import_migration', Path(__file__).parent / 'migrations/versions/canvas004_result_imports.py')
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.base.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {cls.schema} CASCADE'))
        cls.base.dispose()

    def setUp(self):
        self.enterContext(patch.object(api, 'get_engine', lambda: self.engine))
        self.enterContext(patch.dict(os.environ, {'COZE_BACKEND_TOKEN': 'canvas-test-token'}))

    def call(self, action, project=None, payload=None, user='alice'):
        return api.canvas(api.CanvasRequest(user_id=user, action=action, project_id=project, payload=payload or {}), 'Bearer canvas-test-token')

    def create(self):
        return self.call('create', payload={'id': str(uuid.uuid4()), 'title': '测试画布'})['project']

    def save(self, project, **extra):
        return self.call('save', project['id'], {'revision': project['revision'], 'mutationId': str(uuid.uuid4()), 'document': project['document'], **extra})

    def test_assistant_idempotency_and_atomic_application(self):
        project = self.create()
        turn_id = str(uuid.uuid4())
        request = {'id': turn_id, 'revision': 0, 'message': '先整理方向', 'selectedNodeIds': []}
        self.assertTrue(self.call('assistant_start', project['id'], request)['started'])
        self.assertFalse(self.call('assistant_start', project['id'], request)['started'])
        with self.assertRaises(HTTPException):
            self.call('assistant_history', project['id'], user='bob')
        response = {'reply': '已整理', 'toolCalls': [], 'model': 'test'}
        result = self.call('assistant_finish', project['id'], {'id': turn_id, 'document': project['document'], 'response': response})
        self.assertEqual(result['project']['revision'], 1)
        repeat = self.call('assistant_finish', project['id'], {'id': turn_id, 'document': project['document'], 'response': response})
        self.assertEqual(repeat['project']['revision'], 1)
        self.assertEqual(self.call('assistant_history', project['id'])['turns'][0]['status'], 'completed')

    def test_assistant_conflict_preserves_newer_document_and_audit(self):
        project = self.create()
        turn_id = str(uuid.uuid4())
        self.call('assistant_start', project['id'], {'id': turn_id, 'revision': 0, 'message': '整理', 'selectedNodeIds': []})
        newer = self.save(project)['project']
        result = self.call('assistant_finish', project['id'], {'id': turn_id, 'document': project['document'], 'response': {'reply': '旧规划', 'toolCalls': []}})
        self.assertTrue(result['conflict'])
        current = self.call('get', project['id'])['project']
        self.assertEqual(current['revision'], newer['revision'])
        turn = self.call('assistant_history', project['id'])['turns'][0]
        self.assertEqual(turn['status'], 'failed')
        self.assertEqual(turn['response']['reply'], '旧规划')

    def test_assistant_rejects_forged_selection_and_expires_abandoned_turn(self):
        project = self.create()
        turn_id = str(uuid.uuid4())
        request = {'id': turn_id, 'revision': 0, 'message': '整理', 'selectedNodeIds': ['not-owned']}
        with self.assertRaises(HTTPException):
            self.call('assistant_start', project['id'], request)
        request['selectedNodeIds'] = []
        self.call('assistant_start', project['id'], request)
        with self.engine.begin() as conn:
            conn.execute(text('UPDATE canvas_assistant_turns SET created_at=0 WHERE id=:id'), {'id': turn_id})
        self.assertEqual(self.call('assistant_history', project['id'])['turns'][0]['status'], 'failed')
        self.assertFalse(self.call('assistant_start', project['id'], request)['started'])

    def test_assistant_account_rate_limit_does_not_block_idempotent_retry(self):
        user = 'rate-' + uuid.uuid4().hex
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO users VALUES (:user,'active')"), {'user': user})
        project = self.call('create', payload={'id': str(uuid.uuid4())}, user=user)['project']
        for _ in range(10):
            request = {'id': str(uuid.uuid4()), 'revision': 0, 'message': '整理', 'selectedNodeIds': []}
            self.call('assistant_start', project['id'], request, user=user)
            self.call('assistant_fail', project['id'], {'id': request['id'], 'error': 'test'}, user=user)
        self.assertFalse(self.call('assistant_start', project['id'], request, user=user)['started'])
        request['id'] = str(uuid.uuid4())
        with self.assertRaises(HTTPException) as error:
            self.call('assistant_start', project['id'], request, user=user)
        self.assertEqual(error.exception.status_code, 429)

    def test_ownership_and_authentication(self):
        project = self.create()
        with self.assertRaises(HTTPException) as error:
            self.call('get', project['id'], user='bob')
        self.assertEqual(error.exception.status_code, 404)
        with self.assertRaises(HTTPException):
            self.call('list', user='blocked')
        with self.assertRaises(HTTPException):
            api.canvas(api.CanvasRequest(user_id='alice', action='list'), None)

    def test_revision_conflict_and_idempotent_save(self):
        project = self.create()
        mutation = str(uuid.uuid4())
        first = self.save(project, mutationId=mutation)['project']
        self.assertEqual(first['revision'], 1)
        repeat = self.save(project, mutationId=mutation)['project']
        self.assertEqual(repeat['revision'], 1)
        with self.assertRaises(HTTPException) as error:
            self.save(project)
        self.assertEqual(error.exception.status_code, 409)
        self.save(first)
        with self.assertRaises(HTTPException):
            self.save(project, mutationId=mutation)

    def test_concurrent_save_only_one_wins(self):
        project = self.create()
        def attempt(_):
            try:
                return self.save(project)['project']['revision']
            except HTTPException as error:
                return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(attempt, range(2))), [1, 409])

    def test_archive_restore_copy_and_history(self):
        project = self.create()
        archived = self.call('archive', project['id'], {'revision': 0, 'mutationId': str(uuid.uuid4())})['project']
        with self.assertRaises(HTTPException):
            self.save(archived)
        restored = self.call('restore', project['id'], {'revision': 1, 'mutationId': str(uuid.uuid4())})['project']
        self.assertEqual(restored['status'], 'active')
        copied = self.call('copy', project['id'], {'id': str(uuid.uuid4())})['project']
        self.assertNotEqual(copied['id'], project['id'])
        self.assertEqual(copied['document'], project['document'])
        self.assertEqual(len(self.call('versions', project['id'])['versions']), 3)

    def test_asset_owner_validated_on_save(self):
        project = self.create()
        project['document']['nodes'] = [{'id': 'asset-node', 'type': 'asset', 'position': {'x': 0, 'y': 0}, 'data': {'assetId': 'not-owned'}}]
        with self.assertRaises(HTTPException) as error:
            self.save(project)
        self.assertEqual(error.exception.status_code, 404)

    def test_private_upload_and_idempotent_retry(self):
        storage = MagicMock()
        storage.generate_presigned_url.return_value = 'https://storage.invalid/private/file?signature=short'
        payload = {'id': str(uuid.uuid4()), 'fileName': 'sample.png', 'mimeType': 'image/png', 'base64': base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()}
        with patch.object(api, 'get_storage_manager', return_value=MagicMock(storage=storage)), patch.object(api.requests, 'head', return_value=MagicMock(status_code=403)):
            first = self.call('upload', payload=payload)['asset']
            second = self.call('upload', payload=payload)['asset']
        self.assertEqual(first['id'], second['id'])
        self.assertNotIn('object_key', first)
        metadata = self.call('asset', payload={'assetId': first['id']})['asset']
        self.assertEqual(metadata['mime_type'], 'image/png')
        self.assertNotIn('object_key', metadata)
        with self.assertRaises(HTTPException):
            self.call('asset', payload={'assetId': first['id']}, user='bob')
        self.assertEqual(storage._get_client().put_object.call_count, 1)
        self.assertEqual(storage._get_client().put_object.call_args.kwargs['ACL'], 'private')

    def test_result_import_is_owned_atomic_and_not_undone(self):
        project = self.create()
        task_id, asset_id = str(uuid.uuid4()), str(uuid.uuid4())
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO tasks (id,user_id,status) VALUES (:id,'alice','success')"), {'id': task_id})
            conn.execute(text("INSERT INTO canvas_assets (id,user_id,object_key,file_name,mime_type,size,sha256,created_at) VALUES (:id,'alice',:id,'test.png','image/png',16,'test',0)"), {'id': asset_id})
        payload = {'taskId': task_id, 'assetId': asset_id, 'imageIndex': 0}
        with self.assertRaises(HTTPException):
            self.call('import_result', project['id'], payload, user='bob')
        first = self.call('import_result', project['id'], payload)
        self.assertTrue(first['imported'])
        self.assertEqual(len(first['project']['document']['nodes']), 1)
        self.assertFalse(self.call('import_result', project['id'], payload)['imported'])
        restored = self.save(first['project'], document=copy.deepcopy(api.EMPTY))['project']
        retry = self.call('import_result', project['id'], payload)
        self.assertFalse(retry['imported'])
        self.assertEqual(retry['project']['revision'], restored['revision'])
        self.assertEqual(retry['project']['document']['nodes'], [])
        with self.assertRaises(HTTPException):
            self.call('import_result', project['id'], {**payload, 'taskId': 'foreign-task'})
        self.call('archive', project['id'], {'revision': restored['revision'], 'mutationId': str(uuid.uuid4())})
        with self.assertRaises(HTTPException):
            self.call('import_result', project['id'], {**payload, 'imageIndex': 1})

    def test_public_bucket_upload_rejected(self):
        storage = MagicMock()
        storage.generate_presigned_url.return_value = 'https://storage.invalid/public/file?signature=short'
        payload = {'id': str(uuid.uuid4()), 'fileName': 'sample.png', 'mimeType': 'image/png', 'base64': base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()}
        with patch.object(api, 'get_storage_manager', return_value=MagicMock(storage=storage)), patch.object(api.requests, 'head', return_value=MagicMock(status_code=200)):
            with self.assertRaises(HTTPException) as error:
                self.call('upload', payload=payload)
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(storage._get_client().delete_object.call_count, 1)
        with self.engine.connect() as conn:
            self.assertIsNone(conn.execute(text('SELECT id FROM canvas_assets WHERE id=:id'), {'id': payload['id']}).first())

    def test_mime_spoofing_rejected(self):
        with self.assertRaises(HTTPException) as error:
            self.call('upload', payload={'id': str(uuid.uuid4()), 'mimeType': 'image/png', 'base64': base64.b64encode(b'<html>not an image</html>').decode()})
        self.assertEqual(error.exception.status_code, 400)

    def test_run_idempotency_and_atomic_claim(self):
        project = self.create()
        project['document']['nodes'] = [{'id': 'operation', 'type': 'operation', 'position': {'x': 0, 'y': 0}, 'data': {'operation': 'edit'}}]
        project = self.save(project)['project']
        key = str(uuid.uuid4())
        payload = {'revision': project['revision'], 'nodeId': 'operation', 'idempotencyKey': key, 'request': {'assetIds': [], 'input': {'prompt': 'a'}}}
        first = self.call('reserve_run', project['id'], payload)['run']
        second = self.call('reserve_run', project['id'], payload)['run']
        self.assertEqual(first['id'], second['id'])
        altered = copy.deepcopy(payload); altered['request']['input']['prompt'] = 'b'
        with self.assertRaises(HTTPException):
            self.call('reserve_run', project['id'], altered)
        with patch.object(api, 'get_storage_manager', return_value=MagicMock()):
            with ThreadPoolExecutor(max_workers=2) as pool:
                values = list(pool.map(lambda _: self.call('claim_run', project['id'], {'runId': key})['claimed'], range(2)))
        self.assertEqual(sorted(values), [False, True])
        with self.assertRaises(HTTPException):
            self.call('run_task', project['id'], {'runId': key}, user='bob')

    def reserve(self):
        project = self.create()
        project['document']['nodes'] = [{'id': 'op', 'type': 'operation', 'position': {'x': 0, 'y': 0}, 'data': {'label': '编辑'}}]
        project = self.save(project)['project']
        payload = {'revision': project['revision'], 'nodeId': 'op', 'idempotencyKey': str(uuid.uuid4()), 'request': {'assetIds': [], 'input': {'prompt': 'a'}}}
        return project, payload, self.call('reserve_run', project['id'], payload)['run']

    def test_expired_claim_recovered_and_old_worker_fenced(self):
        project, payload, run = self.reserve()
        claim = self.call('claim_run', project['id'], {'runId': run['id']})
        self.assertTrue(claim['claimed'])
        with self.engine.begin() as conn:
            conn.execute(text('UPDATE canvas_runs SET lease_until=0 WHERE id=:id'), {'id': run['id']})
        recovered = self.call('claim_run', project['id'], {'runId': run['id']})
        self.assertTrue(recovered['claimed'])
        self.assertFalse(self.call('begin_run', project['id'], {'runId': run['id'], 'leaseToken': claim['leaseToken']})['accepted'])
        self.assertTrue(self.call('begin_run', project['id'], {'runId': run['id'], 'leaseToken': recovered['leaseToken']})['accepted'])
        with self.engine.begin() as conn:
            conn.execute(text('UPDATE canvas_runs SET lease_until=0 WHERE id=:id'), {'id': run['id']})
        self.assertFalse(self.call('claim_run', project['id'], {'runId': run['id']})['claimed'])

    def test_two_devices_share_active_submission(self):
        project, payload, run = self.reserve()
        payload['idempotencyKey'] = str(uuid.uuid4())
        self.assertEqual(self.call('reserve_run', project['id'], payload)['run']['id'], run['id'])
        payload['request']['input']['prompt'] = 'different'
        with self.assertRaises(HTTPException):
            self.call('reserve_run', project['id'], payload)

    def test_receipts_survive_old_version_restore(self):
        project = self.create()
        old = copy.deepcopy(project['document'])
        project['document']['importedRunIds'] = ['completed-run']
        project = self.save(project)['project']
        project['document'] = old
        restored = self.save(project)['project']
        self.assertEqual(restored['document']['importedRunIds'], ['completed-run'])

    def test_submission_lookup_is_owner_scoped(self):
        project, payload, run = self.reserve()
        other = self.create()
        self.assertIsNone(self.call('find_run', other['id'], {'runId': run['id']})['run'])
        self.assertEqual(self.call('find_run', project['id'], {'runId': run['id']})['run']['id'], run['id'])

    def test_cancel_tombstone_fences_delayed_submission(self):
        project = self.create()
        key = str(uuid.uuid4())
        self.assertTrue(self.call('abort_submission', project['id'], {'runId': key, 'nodeId': 'op'})['cancelled'])
        self.assertEqual(self.call('find_run', project['id'], {'runId': key})['run']['status'], 'failed')
        self.assertFalse(self.call('claim_run', project['id'], {'runId': key})['claimed'])

    def test_dispatch_survives_browser_absence(self):
        project, payload, run = self.reserve()
        jobs = self.call('dispatch_runs')['runs']
        self.assertIn(run['id'], [job['id'] for job in jobs])


if __name__ == '__main__':
    unittest.main()
