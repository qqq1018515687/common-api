from pathlib import Path


ROOT = Path(__file__).parent
STATE_SOURCE = ROOT.joinpath("src/graphs/state.py").read_text(encoding="utf-8")
NODE_SOURCE = ROOT.joinpath("src/graphs/node.py").read_text(encoding="utf-8")


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
