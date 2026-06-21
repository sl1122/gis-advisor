from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = Path("D:/桌面/AutoGIS结果/first_hunan_full_run")
BUNDLED_PYTHON = Path(
    "C:/Users/SL/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
)


def _python_executable() -> str:
    if BUNDLED_PYTHON.exists():
        return str(BUNDLED_PYTHON)
    return sys.executable


def run_first_hunan_competition() -> dict[str, Any]:
    script = ROOT / "scripts" / "run_first_hunan_full.py"
    if not script.exists():
        return {"ok": False, "error": f"Runner script not found: {script}"}

    proc = subprocess.run(
        [_python_executable(), "-X", "utf8", str(script)],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=3600,
    )
    answers_path = DEFAULT_OUTPUT / "answers.json"
    report_path = DEFAULT_OUTPUT / "run_report.md"
    answers = None
    if answers_path.exists():
        answers = json.loads(answers_path.read_text(encoding="utf-8"))

    mismatch_count = 0
    validation = []
    if answers:
        validation = answers.get("FireMSite", {}).get("validation", [])
        mismatch_count = sum(1 for item in validation if item.get("status") == "mismatch")

    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-8000:],
        "output_dir": str(DEFAULT_OUTPUT),
        "report": str(report_path) if report_path.exists() else "",
        "answers": str(answers_path) if answers_path.exists() else "",
        "mismatch_count": mismatch_count,
        "validation": validation,
        "summary": answers,
    }
