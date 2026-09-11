from typing import Literal, Optional, cast


TaskSourceScope = Literal["plugin", "main"]


def normalize_source_scope(value: Optional[str]) -> Optional[TaskSourceScope]:
    if value is None or not value.strip():
        return None
    normalized = value.strip().lower()
    if normalized not in {"plugin", "main"}:
        raise ValueError("source_scope 仅支持 plugin 或 main")
    return cast(TaskSourceScope, normalized)


def matches_task_source(platform: Optional[str], source_scope: Optional[str]) -> bool:
    normalized = normalize_source_scope(source_scope)
    if normalized == "plugin":
        return platform == "plugin"
    if normalized == "main":
        return platform is not None and platform != "plugin"
    return True
