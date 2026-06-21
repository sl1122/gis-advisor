from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".autogis"
HISTORY_PATH = STATE_DIR / "history.json"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _default_history() -> dict[str, Any]:
    return {"recent_projects": [], "runs": []}


def load_history() -> dict[str, Any]:
    if not HISTORY_PATH.exists():
        return _default_history()
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_history()
    data.setdefault("recent_projects", [])
    data.setdefault("runs", [])
    return data


def save_history(data: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_project(folder: str, task: str = "", main_data: str = "", workflow: str = "", output_dir: str = "") -> dict[str, Any]:
    data = load_history()
    folder = folder.strip()
    if not folder:
        return data

    project = {
        "folder": folder,
        "task": task,
        "main_data": main_data,
        "workflow": workflow,
        "output_dir": output_dir,
        "last_opened": _now(),
    }
    existing = [item for item in data["recent_projects"] if item.get("folder") != folder]
    data["recent_projects"] = [project, *existing][:20]
    save_history(data)
    return data


def record_run(
    workflow: str,
    output_dir: str,
    dry_run: bool,
    results: list[dict[str, Any]],
    task: str = "",
    folder: str = "",
    main_data: str = "",
) -> dict[str, Any]:
    data = load_history()
    run = {
        "time": _now(),
        "workflow": workflow,
        "output_dir": output_dir,
        "dry_run": dry_run,
        "task": task,
        "folder": folder,
        "main_data": main_data,
        "summary": {
            "total": len(results),
            "completed": sum(1 for item in results if item.get("status") == "completed"),
            "dry_run": sum(1 for item in results if item.get("status") == "dry_run"),
            "blocked": sum(1 for item in results if item.get("status") == "blocked"),
            "failed": sum(1 for item in results if item.get("status") == "failed"),
            "skipped": sum(1 for item in results if item.get("status") == "skipped"),
        },
        "results": results,
    }
    data["runs"] = [run, *data["runs"]][:50]
    if folder:
        data = record_project(folder, task=task, main_data=main_data, workflow=workflow, output_dir=output_dir)
        data["runs"] = [run, *[item for item in data["runs"] if item != run]][:50]
    save_history(data)
    return data


def clear_history() -> dict[str, Any]:
    data = _default_history()
    save_history(data)
    return data

