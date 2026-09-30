import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from api import prompt_images
from storage.s3.s3_storage import S3SyncStorage


class FakeStorage:
    def __init__(self, oversized=False):
        self.oversized = oversized
        self.read_count = 0

    def read_file(self, *, file_key, max_bytes):
        self.read_count += 1
        assert file_key == "uploads/example.jpg"
        assert max_bytes == prompt_images.MAX_PROMPT_IMAGE_BYTES
        if self.oversized:
            raise ValueError("too large")
        return b"image-bytes"


class FakeStorageManager:
    def __init__(self, owner="user-1", expired=False, oversized=False):
        self.owner = owner
        self.expired = expired
        self.storage = FakeStorage(oversized=oversized)

    def get_file_metadata(self, key):
        assert key == "uploads/example.jpg"
        return {"operator_user_id": self.owner}

    def is_expired(self, key):
        assert key == "uploads/example.jpg"
        return self.expired


class PromptImageReadTests(unittest.TestCase):
    def call_reader(self, user="user-1", authorization="Bearer test-token"):
        return asyncio.run(prompt_images.read_prompt_image(
            prompt_images.PromptImageReadRequest(file_key="uploads/example.jpg", operator_user_id=user),
            authorization=authorization,
        ))

    def test_auth_and_owner_before_read(self):
        manager = FakeStorageManager()
        with patch.dict("os.environ", {"COMMON_SERVICE_TOKEN": "test-token"}), patch.object(prompt_images, "get_storage_manager", return_value=manager):
            with self.assertRaises(HTTPException) as error:
                self.call_reader(authorization=None)
            self.assertEqual(error.exception.status_code, 401)

            with self.assertRaises(HTTPException) as error:
                self.call_reader(user="user-2")
            self.assertEqual(error.exception.status_code, 403)
            self.assertEqual(manager.storage.read_count, 0)

            response = self.call_reader()
            self.assertEqual(response.body, b"image-bytes")
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(manager.storage.read_count, 1)

    def test_expired_and_oversized_objects(self):
        with patch.dict("os.environ", {"COMMON_SERVICE_TOKEN": "test-token"}):
            expired = FakeStorageManager(expired=True)
            with patch.object(prompt_images, "get_storage_manager", return_value=expired):
                with self.assertRaises(HTTPException) as error:
                    self.call_reader()
                self.assertEqual(error.exception.status_code, 410)
                self.assertEqual(expired.storage.read_count, 0)

            oversized = FakeStorageManager(oversized=True)
            with patch.object(prompt_images, "get_storage_manager", return_value=oversized):
                with self.assertRaises(HTTPException) as error:
                    self.call_reader()
                self.assertEqual(error.exception.status_code, 413)


class BoundedStorageReadTests(unittest.TestCase):
    def test_read_file_stops_after_limit_without_content_length(self):
        class Body:
            requested = None
            closed = False

            def read(self, length=None):
                self.requested = length
                return b"oversized"

            def close(self):
                self.closed = True

        body = Body()
        class Client:
            def get_object(self, **kwargs):
                return {"Body": body}

        storage = S3SyncStorage(endpoint_url="https://example.invalid", access_key="x", secret_key="x", bucket_name="test")
        storage._get_client = lambda: Client()
        with self.assertRaises(ValueError):
            storage.read_file(file_key="uploads/example.jpg", max_bytes=3)
        self.assertEqual(body.requested, 4)
        self.assertTrue(body.closed)


if __name__ == "__main__":
    unittest.main()
