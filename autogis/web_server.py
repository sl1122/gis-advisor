from __future__ import annotations

import argparse
import json
import mimetypes
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .ai_analyzer import analyze_task, analyze_task_with_llm, save_case_memory
from .data_inspector import inspect_dataset
from .env import detect_environment
from .executor import execute_workflow
from .folder_scanner import scan_folder
from .guidance import build_guidance
from .history import clear_history, load_history, record_project, record_run
from .knowledge_base import match_knowledge
from .llm_client import PROVIDERS, get_llm_config
from .operation_catalog import build_operation_modules
from .planner import plan_task
from .stat_checker import profile_tables
from .training_reflections import rebuild_training_index, search_training_reflections
from .workflow_memory import save_workflow_memory


ROOT = Path(__file__).resolve().parent.parent
STATIC_ROOT = Path(__file__).resolve().parent / "web"
WORKFLOW_DIR = ROOT / "workflows"
OUTPUT_DIR = ROOT / "project_outputs"
TRAINING_REFLECTION_HTML = Path(r"D:\桌面\训练反思\GIS竞赛心得.html")


def _json_response(handler: BaseHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


def _safe_workflow_path(name: str) -> Path:
    filename = Path(name).name
    if not filename.endswith(".json"):
        filename += ".json"
    return WORKFLOW_DIR / filename


class AutoGISHandler(BaseHTTPRequestHandler):
    server_version = "AutoGISWeb/0.1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"[web] {self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/doctor":
            _json_response(self, detect_environment().to_dict())
            return

        if parsed.path == "/api/workflows":
            WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
            workflows = [
                {"name": path.name, "path": str(path), "size": path.stat().st_size}
                for path in sorted(WORKFLOW_DIR.glob("*.json"))
            ]
            _json_response(self, workflows)
            return

        if parsed.path == "/api/history":
            _json_response(self, load_history())
            return

        if parsed.path == "/api/ai/providers":
            _json_response(
                self,
                {
                    "providers": {
                        name: get_llm_config(name).to_public_dict()
                        for name in PROVIDERS
                    }
                },
            )
            return

        if parsed.path == "/training-reflection":
            if not TRAINING_REFLECTION_HTML.exists():
                self.send_error(HTTPStatus.NOT_FOUND, "Training reflection page not found")
                return
            body = TRAINING_REFLECTION_HTML.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = _read_json(self)

            if parsed.path == "/api/inspect":
                path = payload.get("path", "")
                _json_response(self, inspect_dataset(Path(path)))
                return

            if parsed.path == "/api/scan-folder":
                path = payload.get("path", "")
                max_files = int(payload.get("max_files", 500))
                scan = scan_folder(Path(path), max_files=max_files).to_dict()
                record_project(path)
                _json_response(self, scan)
                return

            if parsed.path == "/api/history/clear":
                _json_response(self, clear_history())
                return

            if parsed.path == "/api/analyze-task":
                task = payload.get("task", "")
                scan = payload.get("scan") or {}
                provider = payload.get("provider", "local")
                model = payload.get("model") or None
                if provider == "local":
                    result = analyze_task(task, scan=scan).to_dict()
                else:
                    result = analyze_task_with_llm(task, scan=scan, provider=provider, model=model)
                result["guidance"] = build_guidance(task, scan=scan).to_dict()
                result["knowledge"] = match_knowledge(task).to_dict()
                result["training_matches"] = search_training_reflections(task)
                _json_response(self, result)
                return

            if parsed.path == "/api/knowledge-match":
                task = payload.get("task", "")
                _json_response(self, {"ok": True, "knowledge": match_knowledge(task).to_dict()})
                return

            if parsed.path == "/api/rebuild-training-index":
                records = rebuild_training_index()
                _json_response(self, {"ok": True, "count": len(records)})
                return

            if parsed.path == "/api/operation-modules":
                task = payload.get("task", "")
                scan = payload.get("scan") or {}
                analysis = payload.get("analysis") or {}
                modules = [item.to_dict() for item in build_operation_modules(task, scan, analysis=analysis)]
                _json_response(self, {"ok": True, "modules": modules})
                return

            if parsed.path == "/api/stat-check":
                task = payload.get("task", "")
                output_dir = Path(payload.get("output_dir") or OUTPUT_DIR / "stat_check")
                paths = [Path(p) for p in payload.get("paths", []) if p]
                _json_response(self, profile_tables(paths, task=task, output_dir=output_dir))
                return

            if parsed.path == "/api/learn-case":
                case = payload.get("case") or {}
                _json_response(self, {"ok": True, "cases": save_case_memory(case)})
                return

            if parsed.path == "/api/plan":
                task = payload.get("task", "")
                data = [Path(p) for p in payload.get("data", []) if p]
                analysis = payload.get("analysis") or {}
                provider = payload.get("provider", "local")
                model = payload.get("model") or None
                scan = payload.get("scan") or {}
                if not analysis:
                    if provider == "local":
                        analysis = analyze_task(task, scan=scan).to_dict()
                    else:
                        analysis = analyze_task_with_llm(task, scan=scan, provider=provider, model=model)
                    analysis["guidance"] = build_guidance(task, scan=scan).to_dict()
                workflow = plan_task(task, data_paths=data, analysis=analysis)
                workflow_payload = workflow.to_dict()
                training_matches = search_training_reflections(task)
                workflow_payload["analysis_used"] = {
                    "mode": analysis.get("mode"),
                    "llm_used": bool((analysis.get("llm") or {}).get("used")),
                    "provider": (analysis.get("llm") or {}).get("provider"),
                }
                workflow_payload["training_matches"] = training_matches
                save_name = payload.get("save_name")
                if save_name:
                    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
                    out = _safe_workflow_path(save_name)
                    out.write_text(
                        json.dumps(workflow_payload, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    workflow_payload["saved_to"] = str(out)
                record_project(
                    payload.get("folder", ""),
                    task=task,
                    main_data=str(data[0]) if data else "",
                    workflow=save_name or "",
                    output_dir=payload.get("output_dir", ""),
                )
                save_case_memory(
                    {
                        "task": task,
                        "task_types": workflow_payload.get("task_types", []),
                        "workflow": save_name or "",
                        "data_paths": [str(item) for item in data],
                        "missing_inputs": workflow_payload.get("missing_inputs", []),
                    }
                )
                save_workflow_memory(
                    {
                        "task": task,
                        "task_types": workflow_payload.get("task_types", []),
                        "step_titles": [step.get("title") for step in workflow_payload.get("steps", [])],
                        "analysis_mode": analysis.get("mode"),
                        "llm_used": bool((analysis.get("llm") or {}).get("used")),
                        "provider": (analysis.get("llm") or {}).get("provider"),
                        "training_matches": training_matches,
                        "missing_inputs": workflow_payload.get("missing_inputs", []),
                    }
                )
                _json_response(self, workflow_payload)
                return

            if parsed.path == "/api/execute":
                workflow_name = payload.get("workflow", "")
                workflow_path = _safe_workflow_path(workflow_name)
                variables = payload.get("variables") or {}
                dry_run = bool(payload.get("dry_run", True))
                output_dir = Path(payload.get("output_dir") or OUTPUT_DIR / workflow_path.stem)
                if not workflow_path.exists():
                    _json_response(
                        self,
                        {
                            "ok": False,
                            "error": "Workflow does not exist.",
                            "path": str(workflow_path),
                        },
                        404,
                    )
                    return
                results = execute_workflow(
                    workflow_path,
                    output_dir,
                    variables=variables,
                    dry_run=dry_run,
                )
                result_payload = [result.to_dict() for result in results]
                record_run(
                    workflow=workflow_name,
                    output_dir=str(output_dir),
                    dry_run=dry_run,
                    results=result_payload,
                    task=payload.get("task", ""),
                    folder=payload.get("folder", ""),
                    main_data=payload.get("main_data", ""),
                )
                _json_response(
                    self,
                    {
                        "output_dir": str(output_dir),
                        "dry_run": dry_run,
                        "results": result_payload,
                    },
                )
                return

            _json_response(self, {"ok": False, "error": "Unknown API endpoint."}, 404)
        except Exception as exc:
            _json_response(self, {"ok": False, "error": str(exc)}, 500)

    def _serve_static(self, request_path: str) -> None:
        if request_path in {"", "/"}:
            request_path = "/index.html"
        relative = request_path.lstrip("/")
        target = (STATIC_ROOT / relative).resolve()
        try:
            target.relative_to(STATIC_ROOT.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type, _ = mimetypes.guess_type(str(target))
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer((host, port), AutoGISHandler)
    url = f"http://{host}:{port}/"
    print(f"AutoGIS Web running at {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="autogis-web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args(argv)
    run_server(args.host, args.port, open_browser=not args.no_open)
    return 0
