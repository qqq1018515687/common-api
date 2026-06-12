#!/usr/bin/env python3
"""Validate favorite image task-result matching behavior."""
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))


database_module = types.ModuleType("coze_coding_dev_sdk.database")
database_module.Base = object
sdk_module = types.ModuleType("coze_coding_dev_sdk")
sdk_module.database = database_module
sys.modules.setdefault("coze_coding_dev_sdk", sdk_module)
sys.modules.setdefault("coze_coding_dev_sdk.database", database_module)


class SimpleBaseModel:
    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)

    def model_copy(self, update: dict | None = None):
        data = self.__dict__.copy()
        if update:
            data.update(update)
        return self.__class__(**data)


def Field(default=..., **_kwargs):
    return None if default is ... else default


class FavoriteImageAdd(SimpleBaseModel):
    pass


class Tasks(SimpleBaseModel):
    pass


class Users(SimpleBaseModel):
    pass


class FavoriteImages(SimpleBaseModel):
    pass


pydantic_module = types.ModuleType("pydantic")
pydantic_module.BaseModel = SimpleBaseModel
pydantic_module.Field = Field
sys.modules.setdefault("pydantic", pydantic_module)

sqlalchemy_exc_module = types.ModuleType("sqlalchemy.exc")
sqlalchemy_exc_module.IntegrityError = Exception
sqlalchemy_orm_module = types.ModuleType("sqlalchemy.orm")
sqlalchemy_orm_module.Session = object
sys.modules.setdefault("sqlalchemy.exc", sqlalchemy_exc_module)
sys.modules.setdefault("sqlalchemy.orm", sqlalchemy_orm_module)

model_module = types.ModuleType("storage.database.shared.model")
model_module.FavoriteImages = FavoriteImages
model_module.Tasks = Tasks
model_module.Users = Users
sys.modules.setdefault("storage.database.shared.model", model_module)

task_manager_module = types.ModuleType("storage.database.task_manager")
task_manager_module.TaskManager = object
sys.modules.setdefault("storage.database.task_manager", task_manager_module)

storage_manager_module = types.ModuleType("storage.storage_manager")
storage_manager_module.StorageCategory = types.SimpleNamespace(FAVORITE="favorite")
storage_manager_module.get_storage_manager = lambda: None
sys.modules.setdefault("storage.storage_manager", storage_manager_module)

module_path = SRC_DIR / "storage" / "database" / "favorite_image_manager.py"
spec = importlib.util.spec_from_file_location("favorite_image_manager_under_test", module_path)
favorite_image_manager = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(favorite_image_manager)

FavoriteImageManager = favorite_image_manager.FavoriteImageManager
FavoriteImageAdd = favorite_image_manager.FavoriteImageAdd


def make_task(**overrides) -> Tasks:
    payload = {
        "id": "task_001",
        "user_id": "user_owner",
        "team_id": "team_001",
        "platform": "test",
        "platform_task_id": "platform_task_001",
        "type": "image",
        "status": "success",
        "created_at": "0",
        "updated_at": "0",
        "result": {
            "imageUrls": [
                "https://img.example.com/a.png",
                "uploads/result-b.png",
                "https://img.example.com/c.png",
            ],
            "thumbnailUrls": [
                "https://img.example.com/a-thumb.png",
                "uploads/result-b-thumb.png",
                "https://img.example.com/c-thumb.png",
            ],
            "previewUrls": [
                "https://img.example.com/a-preview.png",
                "uploads/result-b-preview.png",
                "https://img.example.com/c-preview.png",
            ],
        },
    }
    payload.update(overrides)
    return Tasks(**payload)


def make_favorite(**overrides) -> FavoriteImageAdd:
    payload = {
        "user_id": "user_owner",
        "task_id": "task_001",
        "image_index": 0,
        "source_url": "https://img.example.com/a.png",
    }
    payload.update(overrides)
    return FavoriteImageAdd(**payload)


def make_user(**overrides) -> Users:
    payload = {
        "user_id": "user_owner",
        "team_id": None,
        "role": "user",
    }
    payload.update(overrides)
    return Users(**payload)


class FavoriteImageManagerTest(unittest.TestCase):
    def test_valid_index_and_matching_source_url_are_kept(self) -> None:
        favorite = FavoriteImageManager._normalize_favorite_input_from_task(
            make_favorite(image_index=1, source_url="uploads/result-b.png"),
            make_task(),
        )

        self.assertEqual(1, favorite.image_index)
        self.assertEqual("uploads/result-b.png", favorite.source_url)
        self.assertEqual("uploads/result-b-thumb.png", favorite.thumbnail_url)

    def test_out_of_range_index_is_corrected_by_source_url(self) -> None:
        favorite = FavoriteImageManager._normalize_favorite_input_from_task(
            make_favorite(image_index=99, source_url="https://img.example.com/c.png"),
            make_task(),
        )

        self.assertEqual(2, favorite.image_index)
        self.assertEqual("https://img.example.com/c.png", favorite.source_url)
        self.assertEqual("https://img.example.com/c-thumb.png", favorite.thumbnail_url)

    def test_wrong_index_is_corrected_by_source_url(self) -> None:
        favorite = FavoriteImageManager._normalize_favorite_input_from_task(
            make_favorite(image_index=0, source_url="https://img.example.com/c.png"),
            make_task(),
        )

        self.assertEqual(2, favorite.image_index)
        self.assertEqual("https://img.example.com/c.png", favorite.source_url)

    def test_valid_index_accepts_matching_thumbnail_url_and_keeps_canonical_source(self) -> None:
        favorite = FavoriteImageManager._normalize_favorite_input_from_task(
            make_favorite(image_index=1, source_url="uploads/result-b-thumb.png"),
            make_task(),
        )

        self.assertEqual(1, favorite.image_index)
        self.assertEqual("uploads/result-b.png", favorite.source_url)
        self.assertEqual("uploads/result-b-thumb.png", favorite.thumbnail_url)

    def test_valid_index_accepts_matching_preview_url_and_keeps_canonical_source(self) -> None:
        favorite = FavoriteImageManager._normalize_favorite_input_from_task(
            make_favorite(image_index=2, source_url="https://img.example.com/c-preview.png"),
            make_task(),
        )

        self.assertEqual(2, favorite.image_index)
        self.assertEqual("https://img.example.com/c.png", favorite.source_url)
        self.assertEqual("https://img.example.com/c-thumb.png", favorite.thumbnail_url)

    def test_out_of_range_index_is_corrected_by_source_url_candidates(self) -> None:
        favorite = FavoriteImageManager._normalize_favorite_input_from_task(
            make_favorite(
                image_index=99,
                source_url="https://proxy.example.com/display-thumb.png",
                source_url_candidates=[
                    "https://proxy.example.com/display-thumb.png",
                    "https://img.example.com/c.png",
                ],
            ),
            make_task(),
        )

        self.assertEqual(2, favorite.image_index)
        self.assertEqual("https://img.example.com/c.png", favorite.source_url)

    def test_wrong_index_is_corrected_by_candidate_thumbnail_url(self) -> None:
        favorite = FavoriteImageManager._normalize_favorite_input_from_task(
            make_favorite(
                image_index=0,
                source_url="https://proxy.example.com/display-thumb.png",
                source_url_candidates=["uploads/result-b-thumb.png"],
            ),
            make_task(),
        )

        self.assertEqual(1, favorite.image_index)
        self.assertEqual("uploads/result-b.png", favorite.source_url)

    def test_common_storage_signed_url_matches_task_result_key(self) -> None:
        favorite = FavoriteImageManager._normalize_favorite_input_from_task(
            make_favorite(
                image_index=99,
                source_url="https://common.example.com/file?file_key=uploads/result-b.png&signature=abc",
            ),
            make_task(),
        )

        self.assertEqual(1, favorite.image_index)
        self.assertEqual("uploads/result-b.png", favorite.source_url)

    def test_files_result_file_url_is_used_as_canonical_image_result(self) -> None:
        favorite = FavoriteImageManager._normalize_favorite_input_from_task(
            make_favorite(
                image_index=0,
                source_url="https://rh-images.example.com/result.png",
                source_url_candidates=[
                    "https://rh-images.example.com/result.png",
                    "https://rh-images.example.com/result.png?x-oss-process=image/resize,w_300",
                ],
            ),
            make_task(result={
                "files": [
                    {
                        "file_type": "png",
                        "file_url": "https://rh-images.example.com/result.png",
                    }
                ],
                "message": "success",
            }),
        )

        self.assertEqual(0, favorite.image_index)
        self.assertEqual("https://rh-images.example.com/result.png", favorite.source_url)

    def test_files_result_ignores_non_image_files(self) -> None:
        with self.assertRaisesRegex(ValueError, "这张图片不在原任务结果中，暂时无法收藏"):
            FavoriteImageManager._normalize_favorite_input_from_task(
                make_favorite(
                    image_index=0,
                    source_url="https://files.example.com/result.mp4",
                ),
                make_task(result={
                    "files": [
                        {
                            "file_type": "mp4",
                            "file_url": "https://files.example.com/result.mp4",
                        }
                    ],
                }),
            )

    def test_rejects_source_url_outside_task_result(self) -> None:
        with self.assertRaisesRegex(ValueError, "这张图片不在原任务结果中，暂时无法收藏"):
            FavoriteImageManager._normalize_favorite_input_from_task(
                make_favorite(image_index=99, source_url="https://other.example.com/not-owned.png"),
                make_task(),
            )

    def test_rejects_candidates_outside_task_result(self) -> None:
        with self.assertRaisesRegex(ValueError, "这张图片不在原任务结果中，暂时无法收藏"):
            FavoriteImageManager._normalize_favorite_input_from_task(
                make_favorite(
                    image_index=99,
                    source_url="https://other.example.com/not-owned.png",
                    source_url_candidates=["https://other.example.com/not-owned-thumb.png"],
                ),
                make_task(),
            )

    def test_task_access_keeps_owner_team_and_admin_boundaries(self) -> None:
        task = make_task()

        self.assertTrue(FavoriteImageManager._can_access_task(make_user(user_id="user_owner"), task))
        self.assertTrue(FavoriteImageManager._can_access_task(make_user(user_id="user_peer", team_id="team_001"), task))
        self.assertTrue(FavoriteImageManager._can_access_task(make_user(user_id="admin", role="admin"), task))
        self.assertFalse(FavoriteImageManager._can_access_task(make_user(user_id="user_other", team_id="team_999"), task))


if __name__ == "__main__":
    unittest.main()
