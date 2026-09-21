from pathlib import Path
import ast
from typing import Any, Optional


ROOT = Path(__file__).parent
TASK_MANAGER_PATH = ROOT / "src/storage/database/task_manager.py"


def load_visibility_helper():
    source = TASK_MANAGER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    class_node = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TaskManager"
    )
    method = next(
        node for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_has_visible_media_result"
    )
    namespace = {"Any": Any, "Optional": Optional}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(TASK_MANAGER_PATH), "exec"), namespace)
    return namespace["_has_visible_media_result"]


def test_deleted_url_is_not_visible_through_legacy_result_fields():
    has_visible_media = load_visibility_helper()
    deleted_url = "https://example.test/deleted.jpg"
    result = {
        "imageUrls": [],
        "files": [{"url": deleted_url}],
        "images": [{"url": deleted_url}],
        "thumbnailUrl": "https://example.test/thumb.jpg",
        "previewUrl": "https://example.test/preview.jpg",
    }

    assert has_visible_media(result, [deleted_url]) is False


def test_remaining_media_stays_visible_after_single_image_delete():
    has_visible_media = load_visibility_helper()
    deleted_url = "https://example.test/deleted.jpg"
    active_url = "https://example.test/active.jpg"

    assert has_visible_media({"imageUrls": [deleted_url, active_url]}, [deleted_url]) is True
