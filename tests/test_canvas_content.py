import unittest
from contextlib import contextmanager
from unittest.mock import patch

from api.canvas import canvas_asset_content


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def mappings(self):
        return self


class Connection:
    def execute(self, statement, values):
        sql = str(statement)
        if 'FROM users' in sql:
            return Rows([(1,)])
        if 'FROM canvas_assets' in sql:
            return Rows([{'id': values['id'], 'user_id': values['user'], 'object_key': 'private/image.png', 'mime_type': 'image/png'}])
        raise AssertionError(sql)


class Engine:
    @contextmanager
    def begin(self):
        yield Connection()


class Body:
    def __init__(self):
        self.closed = False

    def iter_chunks(self, chunk_size):
        yield b'\x89PNG'

    def close(self):
        self.closed = True


class Storage:
    def __init__(self, body):
        self.body = body
        self.options = None
        self.storage = self

    def _resolve_bucket(self, bucket):
        return 'private-bucket'

    def _get_client(self):
        return self

    def get_object(self, **options):
        self.options = options
        return {'Body': self.body, 'ContentLength': 4, 'ContentRange': 'bytes 0-3/4'}


class CanvasContentTest(unittest.IsolatedAsyncioTestCase):
    async def test_owned_media_is_streamed_with_range(self):
        body = Body()
        storage = Storage(body)
        with patch('api.canvas.require_backend_authorization'), patch('api.canvas.get_engine', return_value=Engine()), patch('api.canvas.get_storage_manager', return_value=storage):
            response = canvas_asset_content('6a8e5c66-b903-4de4-a135-90ac2cb5ea51', 'owner', authorization='Bearer token', range_header='bytes=0-3')
            chunks = [chunk async for chunk in response.body_iterator]
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.headers['content-type'], 'image/png')
        self.assertEqual(response.headers['content-range'], 'bytes 0-3/4')
        self.assertEqual(storage.options, {'Bucket': 'private-bucket', 'Key': 'private/image.png', 'Range': 'bytes=0-3'})
        self.assertEqual(chunks, [b'\x89PNG'])
        self.assertTrue(body.closed)
