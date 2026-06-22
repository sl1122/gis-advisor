from __future__ import annotations

import argparse
import json
from pathlib import Path

from .data_inspector import inspect_dataset
from .env import detect_environment
from .executor import execute_workflow
from .folder_scanner import scan_folder
from .knowledge_base import run_regression_cases
from .planner import plan_task
from .web_server import run_server


def _print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=True, indent=2))


def cmd_doctor(_: argparse.Namespace) -> int:
    env = detect_environment()
    _print_json(env.to_dict())
    return 0 if env.qgis_process and env.gdalinfo else 1


def cmd_inspect(args: argparse.Namespace) -> int:
    result = inspect_dataset(Path(args.path))
    _print_json(result)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    workflow = plan_task(args.task, data_paths=[Path(p) for p in args.data])
    payload = workflow.to_dict()
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(str(out))
    else:
        _print_json(payload)
    return 0


def cmd_execute(args: argparse.Namespace) -> int:
    variables: dict[str, str] = {}
    for item in args.var:
        if "=" not in item:
            raise SystemExit(f"Invalid variable format: {item}. Use NAME=VALUE.")
        key, value = item.split("=", 1)
        variables[key] = value

    results = execute_workflow(
        workflow_path=Path(args.workflow),
        output_dir=Path(args.output_dir),
        variables=variables,
        dry_run=args.dry_run,
    )
    _print_json([result.to_dict() for result in results])
    return 0 if all(result.status in {"completed", "dry_run", "skipped"} for result in results) else 1


def cmd_scan(args: argparse.Namespace) -> int:
    _print_json(scan_folder(Path(args.folder), max_files=args.max_files).to_dict())
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    run_server(args.host, args.port, open_browser=not args.no_open)
    return 0


def cmd_knowledge_test(args: argparse.Namespace) -> int:
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    result = run_regression_cases(cases)
    _print_json(result)
    return 0 if result.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autogis")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Check QGIS/GDAL/GRASS availability.")
    doctor.set_defaults(func=cmd_doctor)

    inspect = sub.add_parser("inspect", help="Inspect a raster or vector dataset.")
    inspect.add_argument("path")
    inspect.set_defaults(func=cmd_inspect)

    scan = sub.add_parser("scan", help="Scan a project folder and classify likely GIS inputs.")
    scan.add_argument("folder")
    scan.add_argument("--max-files", type=int, default=500)
    scan.set_defaults(func=cmd_scan)

    plan = sub.add_parser("plan", help="Generate a workflow draft from a task.")
    plan.add_argument("task")
    plan.add_argument("--data", action="append", default=[], help="Input data path. Can be repeated.")
    plan.add_argument("--output", help="Write workflow JSON to this path.")
    plan.set_defaults(func=cmd_plan)

    execute = sub.add_parser("execute", help="Execute or preview a workflow JSON.")
    execute.add_argument("workflow")
    execute.add_argument("--output-dir", default="project_outputs")
    execute.add_argument("--var", action="append", default=[], help="Runtime variable, e.g. DEM=D:\\data\\dem.tif")
    execute.add_argument("--dry-run", action="store_true", help="Only print commands, do not run tools.")
    execute.set_defaults(func=cmd_execute)

    web = sub.add_parser("web", help="Start the local web interface.")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--no-open", action="store_true")
    web.set_defaults(func=cmd_web)

    knowledge_test = sub.add_parser("knowledge-test", help="Run knowledge-base regression cases.")
    knowledge_test.add_argument("--cases", default="tests/knowledge_regression.json")
    knowledge_test.set_defaults(func=cmd_knowledge_test)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
