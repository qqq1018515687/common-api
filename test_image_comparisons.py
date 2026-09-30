import hashlib
import hmac
import io
import asyncio
import importlib.util
import os
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi import HTTPException, UploadFile
from PIL import Image
from sqlalchemy import create_engine, text
from starlette.datastructures import Headers

from api import image_comparisons as comparisons


def sign_actor(user_id, timestamp, secret='comparison-test-secret'):
    return hmac.new(secret.encode(), f'image-comparison:{user_id}:{timestamp}'.encode(), hashlib.sha256).hexdigest()


class ImageComparisonTests(unittest.TestCase):
    def test_actor_must_be_signed_for_the_exact_user_and_recent_time(self):
        with patch.dict(os.environ, {'COMMON_SERVICE_TOKEN': 'comparison-test-secret'}):
            now = str(int(time.time()))
            authorization = 'Bearer comparison-test-secret'
            signature = sign_actor('owner-1', now)
            self.assertEqual(comparisons.authenticated_actor(authorization, 'owner-1', now, signature), 'owner-1')
            with self.assertRaises(HTTPException) as wrong_user:
                comparisons.authenticated_actor(authorization, 'owner-2', now, signature)
            self.assertEqual(wrong_user.exception.status_code, 401)
            with self.assertRaises(HTTPException) as expired:
                old = str(int(now) - 360)
                comparisons.authenticated_actor(authorization, 'owner-1', old, sign_actor('owner-1', old))
            self.assertEqual(expired.exception.status_code, 401)
            with self.assertRaises(HTTPException) as unsigned:
                comparisons.authenticated_actor(authorization, 'owner-1', now, None)
            self.assertEqual(unsigned.exception.status_code, 401)

    def test_upload_rejects_disguised_and_oversized_images(self):
        png = io.BytesIO()
        Image.new('RGB', (2, 2), 'white').save(png, format='PNG')
        self.assertEqual(comparisons.validate_image(SimpleNamespace(content_type='image/png'), png.getvalue()), ('image/png', '.png'))
        with self.assertRaises(HTTPException) as disguised:
            comparisons.validate_image(SimpleNamespace(content_type='image/png'), b'not an image')
        self.assertEqual(disguised.exception.status_code, 400)
        with self.assertRaises(HTTPException) as oversized:
            comparisons.validate_image(SimpleNamespace(content_type='image/png'), b'a' * (comparisons.MAX_IMAGE_BYTES + 1))
        self.assertEqual(oversized.exception.status_code, 413)

    def test_public_detail_exposes_no_private_object_key(self):
        with patch.dict(os.environ, {'COMMON_SERVICE_TOKEN': 'comparison-test-secret'}), patch.object(
            comparisons, 'active_share', return_value={
                'token': 'a' * 32, 'title': 'Demo', 'description': '', 'created_at': 1,
                'before_object_key': 'private/a', 'after_object_key': 'private/b',
            },
        ):
            detail = comparisons.get_comparison('a' * 32, authorization='Bearer comparison-test-secret')
        self.assertEqual(detail, {'token': 'a' * 32, 'title': 'Demo', 'description': '', 'createdAt': 1})

    def test_create_anonymous_view_and_owner_revoke(self):
        engine = create_engine('sqlite:///:memory:')
        migration_path = Path(__file__).parent / 'migrations/versions/imagecompare001_public_shares.py'
        spec = importlib.util.spec_from_file_location('imagecompare001', migration_path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE users (user_id TEXT PRIMARY KEY, account_status TEXT)'))
            conn.execute(text("INSERT INTO users VALUES ('owner-1', 'active')"))
            migration.op = Operations(MigrationContext.configure(conn))
            migration.upgrade()

        class FakeStorage:
            def __init__(self):
                self.objects = {}

            def _get_client(self):
                return self

            def _resolve_bucket(self, _):
                return 'private-test-bucket'

            def put_object(self, **kwargs):
                self.objects[kwargs['Key']] = kwargs['Body']

            def delete_object(self, **kwargs):
                self.objects.pop(kwargs['Key'], None)

            def get_object(self, **kwargs):
                return {'Body': io.BytesIO(self.objects[kwargs['Key']])}

            def generate_presigned_url(self, key, expire_time):
                return f'https://private.test/{key}?signature=test'

        storage = FakeStorage()
        png = io.BytesIO()
        Image.new('RGB', (2, 2), 'white').save(png, format='PNG')
        content = png.getvalue()

        def upload(name):
            return UploadFile(file=io.BytesIO(content), filename=name,
                              headers=Headers({'content-type': 'image/png'}))

        now = str(int(time.time()))
        authorization = 'Bearer comparison-test-secret'
        actor = {'authorization': authorization, 'x_comparison_actor': 'owner-1',
                 'x_comparison_actor_time': now, 'x_comparison_actor_signature': sign_actor('owner-1', now)}
        with patch.dict(os.environ, {'COMMON_SERVICE_TOKEN': 'comparison-test-secret'}), \
             patch.object(comparisons, 'get_engine', return_value=engine), \
             patch.object(comparisons, 'get_storage_manager', return_value=SimpleNamespace(storage=storage)), \
             patch.object(comparisons.requests, 'head', return_value=SimpleNamespace(status_code=403)):
            created = asyncio.run(comparisons.create_comparison(
                title='Test', description='Details', before=upload('before.png'), after=upload('after.png'), **actor))
            token = created['token']
            self.assertEqual(len(storage.objects), 2)
            self.assertEqual(comparisons.get_comparison(token, authorization)['title'], 'Test')
            self.assertEqual(comparisons.list_comparisons(**actor)['shares'][0]['token'], token)
            image = comparisons.get_comparison_image(token, 'before', authorization)

            async def read_image():
                return b''.join([part async for part in image.body_iterator])

            self.assertEqual(asyncio.run(read_image()), content)
            with self.assertRaises(HTTPException) as another_user:
                comparisons.revoke_comparison(token, authorization, 'owner-2', now, sign_actor('owner-2', now))
            self.assertEqual(another_user.exception.status_code, 404)
            comparisons.revoke_comparison(token, **actor)
            self.assertEqual(storage.objects, {})
            with self.assertRaises(HTTPException) as revoked:
                comparisons.get_comparison(token, authorization)
            self.assertEqual(revoked.exception.status_code, 404)


if __name__ == '__main__':
    unittest.main()
