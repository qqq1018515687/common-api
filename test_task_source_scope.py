from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))

from storage.database.task_source_scope import (  # noqa: E402
    matches_task_source,
    normalize_source_scope,
)


STATE_SOURCE = ROOT.joinpath("src/graphs/state.py").read_text(encoding="utf-8")
NODE_SOURCE = ROOT.joinpath("src/graphs/node.py").read_text(encoding="utf-8")
TASK_MANAGER_SOURCE = ROOT.joinpath("src/storage/database/task_manager.py").read_text(encoding="utf-8")


def test_source_scope_semantics():
    assert matches_task_source("plugin", "plugin") is True
    assert matches_task_source("tudou", "plugin") is False
    assert matches_task_source("plugin", "main") is False
    assert matches_task_source("tudou", "main") is True
    assert matches_task_source(None, "main") is False


def test_source_scope_rejects_unknown_values():
    with pytest.raises(ValueError, match="plugin 或 main"):
        normalize_source_scope("other")


def test_source_scope_is_carried_through_state_route_and_queries():
    assert STATE_SOURCE.count('source_scope: Optional[Literal["plugin", "main"]]') >= 9
    assert "source_scope=input_data.source_scope" in NODE_SOURCE
    assert "source_scope=state.source_scope" in NODE_SOURCE
    for method in (
        "get_tasks_flexible",
        "get_admin_tasks_compact",
        "count_tasks_with_media",
        "count_tasks_flexible",
        "count_tasks_stats",
        "get_today_success_rate",
    ):
        section = TASK_MANAGER_SOURCE.split(f"def {method}(", 1)[1]
        assert "source_scope: Optional[str]" in section.split(")", 1)[0]


def test_node_rejects_platform_and_source_scope_conflict():
    assert NODE_SOURCE.count('"platform 与 source_scope 不能同时传入"') == 3


def test_admin_compact_does_not_filter_completed_tasks_without_result():
    compact_section = TASK_MANAGER_SOURCE.split("def get_admin_tasks_compact(", 1)[1].split(
        "def _compact_large_base64_fields", 1
    )[0]
    assert "Tasks.result" in compact_section
    assert "media_filter" not in compact_section
    assert ".filter(Tasks.result" not in compact_section
