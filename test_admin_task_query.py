from pathlib import Path


ROOT = Path(__file__).parent
STATE_SOURCE = ROOT.joinpath("src/graphs/state.py").read_text(encoding="utf-8")
NODE_SOURCE = ROOT.joinpath("src/graphs/node.py").read_text(encoding="utf-8")
TASK_MANAGER_SOURCE = ROOT.joinpath("src/storage/database/task_manager.py").read_text(encoding="utf-8")


def test_get_task_accepts_trusted_admin_without_target_user_id():
    state_section = STATE_SOURCE.split("class GetTaskInput", 1)[1].split(
        "class GetTaskOutput", 1
    )[0]
    node_section = NODE_SOURCE.split("def get_task_node(", 1)[1].split(
        "def delete_task_node(", 1
    )[0]

    assert "operator_role: Optional[str]" in state_section
    assert 'is_admin_operator = (state.operator_role or "").strip().lower() == "admin"' in node_section
    assert "if not is_admin_operator and not state.user_id" in node_section
    assert "if not is_admin_operator:" in node_section
    assert "if not requester_is_admin and db_task.user_id != state.user_id" in node_section


def test_admin_task_queries_return_username_and_deleted_images():
    get_section = NODE_SOURCE.split("def get_task_node(", 1)[1].split(
        "def delete_task_node(", 1
    )[0]
    compact_section = TASK_MANAGER_SOURCE.split("def get_admin_tasks_compact(", 1)[1].split(
        "def _compact_large_base64_fields", 1
    )[0]

    assert '"username": task_username' in get_section
    assert '"deleted_image_urls": db_task.deleted_image_urls' in get_section
    assert "Tasks.deleted_image_urls" in compact_section
    assert '"deleted_image_urls": row.deleted_image_urls' in compact_section


def test_personal_history_keeps_user_deleted_images():
    list_section = NODE_SOURCE.split("def list_tasks_node(", 1)[1].split(
        "def count_tasks_stats_node(", 1
    )[0]

    assert "task_mgr._has_visible_media_result(task.result, task.deleted_image_urls)" in list_section
    assert "state.include_deleted_image_results" in list_section
    assert "include_deleted_image_urls=bool(state.include_deleted_image_results)" in list_section
    assert "while len(task_list) <= limit and raw_has_more" in list_section
    assert STATE_SOURCE.count("include_deleted_image_results: Optional[bool]") >= 5
    assert "include_deleted_image_results=input_data.include_deleted_image_results" in NODE_SOURCE
    assert "include_deleted_image_results=state.include_deleted_image_results" in NODE_SOURCE
