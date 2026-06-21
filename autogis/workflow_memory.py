from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
MEMORY_PATH = ROOT / ".autogis" / "workflow_memory.json"


def load_workflow_memory() -> list[dict[str, Any]]:
    if not MEMORY_PATH.exists():
        return []
    try:
        data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def save_workflow_memory(record: dict[str, Any]) -> list[dict[str, Any]]:
    task = (record.get("task") or "").strip()
    if not task:
        return load_workflow_memory()
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    records = [item for item in load_workflow_memory() if item.get("task") != task]
    records.insert(0, record)
    records = records[:200]
    MEMORY_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return records
