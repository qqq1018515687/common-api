import json
import unittest
from fastapi import HTTPException

from api.canvas_imports import _complete


class Rows:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class ImportConnection:
    def __init__(self, document, receipts=(), task_id='task'):
        self.document = document
        self.receipts = list(receipts)
        self.writes = []
        self.job = {'task_id': task_id, 'project_id': 'project', 'user_id': 'owner', 'status': 'processing', 'lease_token': 'token', 'lease_until': 100000}
        self.task = {'id': task_id, 'status': 'completed', 'is_deleted': False, 'parameter_snapshot': {'canvasTarget': {'projectId': 'project'}, 'workflowName': '图像生成'},
                     'workflow_parameters': {'model_name': 'model1'}, 'created_at': '100', 'updated_at': '200', 'source_fingerprint': 'source-a'}

    def execute(self, statement, values=None):
        sql = str(statement)
        values = values or {}
        if sql.startswith('SELECT * FROM canvas_import_jobs'):
            return Rows([self.job])
        if sql.startswith('SELECT t.id,t.status,t.is_deleted,t.parameter_snapshot,t.workflow_parameters'):
            return Rows([self.task])
        if sql.startswith('SELECT * FROM canvas_projects'):
            return Rows([{'id': 'project', 'user_id': 'owner', 'status': 'active', 'revision': 3, 'document': self.document}])
        if sql.startswith('SELECT id,mime_type FROM canvas_assets'):
            return Rows([{'id': values['id'], 'mime_type': 'image/png'}])
        if sql.startswith('SELECT image_index,asset_id FROM canvas_result_imports'):
            return Rows(self.receipts)
        self.writes.append((sql, values))
        return Rows()


def empty_document():
    return {'schemaVersion': 1, 'nodes': [], 'edges': [], 'viewport': {'x': 0, 'y': 0, 'zoom': 1}, 'importedRunIds': []}


class CanvasImportsTest(unittest.TestCase):
    def test_two_outputs_become_one_versioned_card(self):
        conn = ImportConnection(empty_document())
        result = _complete(conn, 'owner', {'taskId': 'task', 'leaseToken': 'token', 'sourceFingerprint': 'source-a', 'assetIds': ['a', 'b']}, 1000)
        self.assertEqual(result['status'], 'completed')
        project_write = next(values for sql, values in conn.writes if sql.startswith('UPDATE canvas_projects'))
        nodes = json.loads(project_write['document'])['nodes']
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]['data']['versions'][0]['assetIds'], ['a', 'b'])
        self.assertEqual(sum(sql.startswith('INSERT INTO canvas_result_imports') for sql, _ in conn.writes), 2)

    def test_two_independent_tasks_both_enter_same_project(self):
        first = ImportConnection(empty_document(), task_id='first')
        _complete(first, 'owner', {'taskId': 'first', 'leaseToken': 'token', 'sourceFingerprint': 'source-a', 'assetIds': ['first-asset']}, 1000)
        first_write = next(values for sql, values in first.writes if sql.startswith('UPDATE canvas_projects'))
        second = ImportConnection(json.loads(first_write['document']), task_id='second')
        _complete(second, 'owner', {'taskId': 'second', 'leaseToken': 'token', 'sourceFingerprint': 'source-a', 'assetIds': ['second-asset']}, 1000)
        second_write = next(values for sql, values in second.writes if sql.startswith('UPDATE canvas_projects'))
        cards = json.loads(second_write['document'])['nodes']
        self.assertEqual({card['data']['sourceTaskId'] for card in cards}, {'first', 'second'})

    def test_repeated_completion_does_not_add_revision(self):
        document = empty_document()
        document['nodes'].append({'id': 'node', 'type': 'asset', 'position': {'x': 0, 'y': 0},
            'data': {'label': '结果', 'assetId': 'a', 'sourceTaskId': 'task', 'versions': [{'id': 'task', 'assetIds': ['a', 'b'], 'createdAt': 100}]}})
        conn = ImportConnection(document, [{'image_index': 0, 'asset_id': 'a'}, {'image_index': 1, 'asset_id': 'b'}])
        self.assertEqual(_complete(conn, 'owner', {'taskId': 'task', 'leaseToken': 'token', 'sourceFingerprint': 'source-a', 'assetIds': ['a', 'b']}, 1000)['status'], 'completed')
        self.assertFalse(any(sql.startswith('UPDATE canvas_projects') for sql, _ in conn.writes))

    def test_removed_card_is_not_recreated(self):
        conn = ImportConnection(empty_document(), [{'image_index': 0, 'asset_id': 'a'}])
        self.assertEqual(_complete(conn, 'owner', {'taskId': 'task', 'leaseToken': 'token', 'sourceFingerprint': 'source-a', 'assetIds': ['a']}, 1000)['status'], 'skipped')
        self.assertFalse(any(sql.startswith('UPDATE canvas_projects') for sql, _ in conn.writes))

    def test_result_changed_after_claim_requires_reclaim(self):
        conn = ImportConnection(empty_document())
        conn.task['source_fingerprint'] = 'source-b'
        with self.assertRaises(HTTPException) as error:
            _complete(conn, 'owner', {'taskId': 'task', 'leaseToken': 'token', 'sourceFingerprint': 'source-a', 'assetIds': ['a']}, 1000)
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse(any(sql.startswith('UPDATE canvas_projects') for sql, _ in conn.writes))

    def test_existing_receipt_does_not_replace_new_image_at_same_position(self):
        document = empty_document()
        document['nodes'].append({'id': 'node', 'type': 'asset', 'position': {'x': 0, 'y': 0},
            'data': {'label': '结果', 'assetId': 'a', 'sourceTaskId': 'task', 'versions': [{'id': 'task', 'assetIds': ['a'], 'createdAt': 100}]}})
        conn = ImportConnection(document, [{'image_index': 0, 'asset_id': 'a'}])
        _complete(conn, 'owner', {'taskId': 'task', 'leaseToken': 'token', 'sourceFingerprint': 'source-a', 'assetIds': ['b']}, 1000)
        project_write = next(values for sql, values in conn.writes if sql.startswith('UPDATE canvas_projects'))
        self.assertEqual(json.loads(project_write['document'])['nodes'][0]['data']['versions'][0]['assetIds'], ['a', 'b'])
        new_receipts = [values for sql, values in conn.writes if sql.startswith('INSERT INTO canvas_result_imports')]
        self.assertEqual([(row['index'], row['asset']) for row in new_receipts], [(1, 'b')])


if __name__ == '__main__':
    unittest.main()
