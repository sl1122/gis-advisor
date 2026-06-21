from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .env import detect_environment


PLACEHOLDER_RE = re.compile(r"<([A-Za-z0-9_]+)>")
SPATIAL_PATH_SUFFIXES = (".tif", ".tiff", ".gpkg", ".shp", ".csv", ".dbf", ".xlsx", ".vrt")
TOOL_ERROR_RE = re.compile(r"(^|\n)\s*(ERROR|CRITICAL)\b|Process returned error code|Traceback|panic", re.IGNORECASE)


@dataclass
class ExecutionResult:
    step_id: str
    status: str
    command: list[str] | None = None
    message: str | None = None
    returncode: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    outputs: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status,
            "command": self.command,
            "message": self.message,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "outputs": self.outputs,
        }


def _resolve_value(value: Any, variables: dict[str, str], output_dir: Path) -> str:
    if isinstance(value, str):
        resolved = value
        for key in PLACEHOLDER_RE.findall(resolved):
            replacement = variables.get(key) or variables.get(key.upper()) or variables.get(key.lower())
            if replacement:
                resolved = resolved.replace(f"<{key}>", replacement)
        threshold = variables.get("threshold") or variables.get("THRESHOLD")
        if threshold:
            resolved = re.sub(r"\bthreshold\b", threshold, resolved)
        distance = variables.get("distance") or variables.get("DISTANCE")
        if distance and resolved == "<distance>":
            resolved = distance
        if resolved.endswith(SPATIAL_PATH_SUFFIXES) and not Path(resolved).is_absolute():
            return str(output_dir / resolved)
        return resolved
    return str(value)


def _merged_args(step: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    merged.update(step.get("inputs") or {})
    merged.update(step.get("parameters") or {})
    merged.update(step.get("outputs") or {})
    return merged


def _build_qgis_command(step: dict[str, Any], qgis_process: str, variables: dict[str, str], output_dir: Path) -> list[str]:
    command = [qgis_process, "run", step["algorithm"], "--"]
    for key, value in _merged_args(step).items():
        command.append(f"{key}={_resolve_value(value, variables, output_dir)}")
    return command


def _build_whitebox_command(step: dict[str, Any], whitebox_tools: str, variables: dict[str, str], output_dir: Path) -> list[str]:
    command = [whitebox_tools, f"-r={step['algorithm']}", "-v"]
    for key, value in _merged_args(step).items():
        resolved = _resolve_value(value, variables, output_dir)
        command.append(f"--{key}={resolved}")
    return command


def _resolved_outputs(step: dict[str, Any], variables: dict[str, str], output_dir: Path) -> list[str]:
    outputs = step.get("outputs") or {}
    return [_resolve_value(value, variables, output_dir) for value in outputs.values()]


def _looks_like_data_path(value: str) -> bool:
    lower = value.lower()
    return lower.endswith(SPATIAL_PATH_SUFFIXES) or bool(re.search(r"[\\/]", value))


def _missing_input_paths(step: dict[str, Any], variables: dict[str, str], output_dir: Path) -> list[str]:
    missing: list[str] = []
    for value in (step.get("inputs") or {}).values():
        resolved = _resolve_value(value, variables, output_dir)
        if PLACEHOLDER_RE.search(resolved):
            continue
        if _looks_like_data_path(resolved) and not Path(resolved).exists():
            missing.append(resolved)
    return missing


def _unresolved_tokens(command: list[str]) -> list[str]:
    tokens: set[str] = set()
    for part in command:
        tokens.update(PLACEHOLDER_RE.findall(part))
        if re.search(r"\bthreshold\b", part):
            tokens.add("threshold")
    return sorted(tokens)


def _blocked_message(tokens: list[str]) -> str:
    hints = {
        "threshold": "threshold=汇流累积量阈值，例如 500",
        "distance": "distance=缓冲距离，单位按当前投影坐标，一般为米，例如 500",
        "DEM": "DEM=高程栅格路径",
        "OBSERVER_POINTS": "OBSERVER_POINTS=观察点图层路径",
        "OBSERVER_XY": "OBSERVER_XY=单个观察点坐标，例如 37521165,3318598",
        "observer_height": "observer_height=观察高度，例如 10",
        "MAX_DISTANCE": "MAX_DISTANCE=最大可视距离或分析半径，单位按 DEM 当前投影坐标，例如 5000",
        "TARGET_LAYER": "TARGET_LAYER=要处理的目标矢量图层",
        "JOIN_TABLE": "JOIN_TABLE=CSV/XLSX/DBF 等连接表路径",
        "TARGET_FIELD": "TARGET_FIELD=目标图层中的连接字段名",
        "JOIN_FIELD": "JOIN_FIELD=连接表中的匹配字段名",
        "FIELDS_TO_COPY": "FIELDS_TO_COPY=要复制的字段；不确定时可先留空或填写字段名",
        "ZONE_LAYER": "ZONE_LAYER=用于分区统计的面图层",
        "ZONE_FIELD": "ZONE_FIELD=分区编号字段，例如 id、name 或行政区代码",
        "VALUE_RASTER": "VALUE_RASTER=被统计的栅格数据路径",
        "STATS": "STATS=统计项，例如 mean,sum,count",
        "TEMPLATE_LAYER": "TEMPLATE_LAYER=创建要素时参考字段结构的模板图层",
        "SPLIT_LAYER": "SPLIT_LAYER=用于切割目标要素的线图层",
        "OVERLAY_LAYER": "OVERLAY_LAYER=裁剪、叠置或遮罩边界图层",
        "GEOMETRY_TYPE": "GEOMETRY_TYPE=要创建的要素类型，例如 point、line、polygon",
        "DELTA_X": "DELTA_X=X 方向移动量，单位按当前投影坐标",
        "DELTA_Y": "DELTA_Y=Y 方向移动量，单位按当前投影坐标",
        "ANGLE": "ANGLE=旋转角度，单位为度",
        "ANCHOR": "ANCHOR=旋转中心，例如 0,0 或明确坐标点",
        "MAX_NODES": "MAX_NODES=划分复杂要素时的最大节点数，例如 256",
        "BUILDING_LAYER": "BUILDING_LAYER=建筑面或建筑轮廓转面后的图层",
        "BUILDING_3D": "BUILDING_3D=具有高度或 Z 值的三维建筑图层",
        "HEIGHT_FIELD": "HEIGHT_FIELD=建筑高度字段；若只有楼层数字段，需要先按楼层数乘以层高生成高度字段",
        "CELL_SIZE": "CELL_SIZE=建筑栅格化像元大小，单位按当前投影坐标",
        "SUN_AZIMUTH": "SUN_AZIMUTH=太阳方位角；冬至正午示例为 180",
        "SUN_ALTITUDE": "SUN_ALTITUDE=太阳高度角；训练反思示例为 44.3",
        "SUN_DATETIME": "SUN_DATETIME=3D 太阳阴影体分析日期时间",
        "CANDIDATE_POINTS": "CANDIDATE_POINTS=候选建筑质心点或候选设施点",
    }
    items = [hints.get(token, f"{token}=请填写对应参数或数据路径") for token in tokens]
    return "缺少运行参数：" + "；".join(items) + "。请在右侧“参数、图层与字段映射”中填写后重新预览。"


def _missing_input_message(paths: list[str]) -> str:
    shown = "；".join(paths[:3])
    extra = f"；另有 {len(paths) - 3} 个" if len(paths) > 3 else ""
    return f"输入数据不存在或上一步没有产出结果：{shown}{extra}。请先运行前置步骤，或在参数映射中改成真实存在的数据路径。"


def _vector_field_names(path: str, ogrinfo: str | None) -> list[str]:
    if not ogrinfo or not Path(path).exists():
        return []
    completed = subprocess.run(
        [ogrinfo, "-json", "-so", path],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if completed.returncode != 0:
        return []
    try:
        info = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    fields: list[str] = []
    for layer in info.get("layers", []):
        for field in layer.get("fields", []):
            name = field.get("name")
            if name:
                fields.append(str(name))
    return fields


def _field_check_message(field_name: str, input_path: str, available_fields: list[str]) -> str:
    fields_text = "、".join(available_fields) if available_fields else "未读取到字段"
    return (
        f"字段不存在：{field_name}。输入图层：{input_path}。"
        f"当前可用字段：{fields_text}。请在“参数、图层与字段映射”中选择真实字段；"
        "如果只有楼层数字段，需要先新增高度字段（楼层数 × 层高）再执行。"
    )


def _field_validation_message(step: dict[str, Any], variables: dict[str, str], output_dir: Path, ogrinfo: str | None) -> str | None:
    merged = _merged_args(step)
    field_value = merged.get("FIELD")
    input_value = merged.get("INPUT")
    if not field_value or not input_value:
        return None
    field_name = _resolve_value(field_value, variables, output_dir)
    input_path = _resolve_value(input_value, variables, output_dir)
    if PLACEHOLDER_RE.search(field_name) or PLACEHOLDER_RE.search(input_path):
        return None
    if not _looks_like_data_path(input_path) or not Path(input_path).exists():
        return None
    available_fields = _vector_field_names(input_path, ogrinfo)
    if available_fields and field_name not in available_fields:
        return _field_check_message(field_name, input_path, available_fields)
    return None


def _build_command(step: dict[str, Any], variables: dict[str, str], output_dir: Path, env: Any) -> tuple[list[str] | None, str | None]:
    engine = step.get("engine")
    if engine == "qgis_processing":
        if not env.qgis_process:
            return None, "未找到 qgis_process，请确认 QGIS 已安装并加入可检测路径。"
        return _build_qgis_command(step, env.qgis_process, variables, output_dir), None
    if engine == "whitebox":
        if not env.whitebox_tools:
            return None, "未找到 WhiteboxTools，请先安装 whitebox 或配置 whitebox_tools。"
        return _build_whitebox_command(step, env.whitebox_tools, variables, output_dir), None
    return None, f"当前步骤暂不能自动执行，需人工确认或后续接入模块：{engine}"


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=3600,
    )


def execute_workflow(
    workflow_path: Path,
    output_dir: Path,
    variables: dict[str, str] | None = None,
    dry_run: bool = True,
) -> list[ExecutionResult]:
    variables = variables or {}
    output_dir.mkdir(parents=True, exist_ok=True)
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    env = detect_environment()
    results: list[ExecutionResult] = []

    for step in workflow.get("steps", []):
        step_id = step.get("id", "<unknown>")
        step_outputs = _resolved_outputs(step, variables, output_dir)
        command, command_error = _build_command(step, variables, output_dir, env)

        if command_error:
            status = "failed" if step.get("engine") in {"qgis_processing", "whitebox"} else "skipped"
            results.append(ExecutionResult(step_id=step_id, status=status, message=command_error, outputs=step_outputs))
            continue

        assert command is not None
        unresolved = _unresolved_tokens(command)
        if unresolved:
            results.append(
                ExecutionResult(
                    step_id=step_id,
                    status="blocked",
                    command=command,
                    message=_blocked_message(unresolved),
                    outputs=step_outputs,
                )
            )
            continue

        if dry_run:
            results.append(ExecutionResult(step_id=step_id, status="dry_run", command=command, outputs=step_outputs))
            continue

        missing_paths = _missing_input_paths(step, variables, output_dir)
        if missing_paths:
            results.append(
                ExecutionResult(
                    step_id=step_id,
                    status="blocked",
                    command=command,
                    message=_missing_input_message(missing_paths),
                    outputs=step_outputs,
                )
            )
            continue

        field_message = _field_validation_message(step, variables, output_dir, env.ogrinfo)
        if field_message:
            results.append(
                ExecutionResult(
                    step_id=step_id,
                    status="blocked",
                    command=command,
                    message=field_message,
                    outputs=step_outputs,
                )
            )
            continue

        completed = _run_command(command)
        stderr = completed.stderr or ""
        stdout = completed.stdout or ""
        failed = completed.returncode != 0 or bool(TOOL_ERROR_RE.search(stderr) or TOOL_ERROR_RE.search(stdout))
        results.append(
            ExecutionResult(
                step_id=step_id,
                status="failed" if failed else "completed",
                command=command,
                returncode=completed.returncode,
                stdout=stdout,
                stderr=stderr,
                outputs=step_outputs,
            )
        )

    return results
