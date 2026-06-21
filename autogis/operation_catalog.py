from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .env import detect_environment


ROOT = Path(__file__).resolve().parent
MODULE_LIBRARY_PATH = ROOT / "module_library.json"


@dataclass
class OperationModule:
    id: str
    title: str
    category: str
    data_group: str
    status: str
    backend: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    sources: list[dict[str, str]] = field(default_factory=list)
    task_order: int = 999999
    task_excerpt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "data_group": self.data_group,
            "status": self.status,
            "backend": self.backend,
            "inputs": self.inputs,
            "steps": self.steps,
            "outputs": self.outputs,
            "checks": self.checks,
            "blockers": self.blockers,
            "sources": self.sources,
            "task_order": self.task_order,
            "task_excerpt": self.task_excerpt,
        }


def load_module_library() -> dict[str, Any]:
    return json.loads(MODULE_LIBRARY_PATH.read_text(encoding="utf-8"))


def _items(scan: dict[str, Any], role: str) -> list[dict[str, Any]]:
    return ((scan.get("groups") or {}).get(role) or [])


def _names(items: list[dict[str, Any]]) -> list[str]:
    return [item.get("name") or item.get("path") or "" for item in items]


def _role_items(scan: dict[str, Any], roles: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for role in roles:
        result.extend(_items(scan, role))
    return result


def _keyword_score(task: str, keywords: list[str]) -> int:
    lowered = task.lower()
    return sum(1 for keyword in keywords if keyword.lower() in lowered)


def _first_keyword_index(task: str, keywords: list[str]) -> int:
    lowered = task.lower()
    indexes = [lowered.find(keyword.lower()) for keyword in keywords if keyword.lower() in lowered]
    return min(indexes) if indexes else 999999


def _excerpt_at(text: str, index: int, radius: int = 80) -> str:
    if index >= 999999:
        return ""
    return text[max(0, index - radius) : min(len(text), index + radius)].strip()


def _backend_available(backends: list[str]) -> bool:
    env = detect_environment()
    for backend in backends:
        lowered = backend.lower()
        if "whitebox" in lowered and env.whitebox_tools:
            return True
        if "qgis" in lowered and env.qgis_process:
            return True
        if "gdal" in lowered and env.gdalinfo:
            return True
        if "grass" in lowered and env.grass:
            return True
        if lowered in {"local_rules", "llm", "pyqgis"}:
            return True
    return False


def _status_from_policy(module: dict[str, Any], scan: dict[str, Any]) -> tuple[str, list[str]]:
    required = module.get("input_roles") or []
    optional = module.get("optional_roles") or []
    policy = module.get("status_policy") or "needs_confirmation"
    backends = module.get("backend") or []
    blockers = list(module.get("blockers") or [])
    has_any_required = bool(_role_items(scan, required))
    missing_roles = [role for role in required if not _items(scan, role)]

    if policy == "needs_plugin" and not _backend_available(backends):
        blockers.append("需要安装或启用对应插件/后端。")
        return "blocked", blockers
    if not has_any_required and required:
        blockers.append(f"未识别到所需数据角色：{', '.join(missing_roles)}")
        return "blocked", blockers
    if policy == "ready":
        return "ready", blockers
    if policy == "ready_when_any_input":
        return ("ready" if has_any_required or _role_items(scan, optional) else "blocked"), blockers
    if policy == "needs_mapping":
        return "needs_mapping", blockers
    if policy == "needs_plugin":
        return "needs_mapping", blockers
    return "needs_confirmation", blockers


def _analysis_allowed_module_ids(analysis: dict[str, Any] | None) -> set[str]:
    if not analysis:
        return set()
    guidance = analysis.get("guidance") or {}
    llm_analysis = (analysis.get("llm") or {}).get("analysis") or {}
    signal = {
        "task_types": analysis.get("task_types") or [],
        "guidance_category": guidance.get("task_category") or "",
        "guidance_evidence": guidance.get("evidence") or [],
        "llm_task_types": llm_analysis.get("task_types") or [],
        "llm_operations": llm_analysis.get("candidate_operations") or [],
        "llm_workflow": llm_analysis.get("workflow_outline") or [],
        "llm_formula": llm_analysis.get("formula_interpretation") or [],
    }
    text = json.dumps(signal, ensure_ascii=False).lower()
    allowed: set[str] = set()
    rules = {
        "hydrology_whitebox": ["水文", "hydrology", "汇流", "河网"],
        "terrain_analysis": ["地形", "terrain", "tci", "坡度", "坡向", "山体阴影"],
        "building_sunlight": ["建筑日照", "sunlight", "太阳阴影", "背光面", "冬至"],
        "viewshed_analysis": ["可视域", "viewshed", "瞭望塔", "观察点"],
        "zonal_statistics": ["分区统计", "zonal", "乡镇", "均值"],
        "field_calculator": ["属性表", "字段", "连接", "join"],
        "raster_calculator_reclass": ["重分类", "栅格计算", "nodata", "变化编码"],
        "remote_sensing_otb": ["遥感", "remote", "ndvi", "分类", "夜间灯光"],
        "suitability_mce": ["选址", "适宜", "约束", "权重"],
        "network_qneat3": ["网络分析", "最短路径", "服务区", "od 矩阵", "od矩阵", "最近设施"],
        "vector_edit_geometry": ["创建要素", "移动", "旋转", "切割", "分割", "裁剪", "几何"],
        "cartography_export": ["制图", "图例", "比例尺", "指北针", "专题图"],
    }
    for module_id, needles in rules.items():
        if any(needle.lower() in text for needle in needles):
            allowed.add(module_id)
    if analysis.get("ok") is not False:
        allowed.add("task_splitter")
    return allowed


def _can_activate_from_inputs(raw: dict[str, Any]) -> bool:
    return raw.get("id") in {"data_standardize", "cartography_export"}


def build_operation_modules(task: str, scan: dict[str, Any], analysis: dict[str, Any] | None = None) -> list[OperationModule]:
    library = load_module_library()
    sources = library.get("sources") or []
    modules: list[tuple[int, OperationModule]] = []
    allowed_by_analysis = _analysis_allowed_module_ids(analysis)

    for raw in library.get("modules", []):
        keywords = raw.get("keywords") or []
        required = raw.get("input_roles") or []
        optional = raw.get("optional_roles") or []
        score = _keyword_score(task, keywords)
        task_order = _first_keyword_index(task, keywords)
        task_excerpt = _excerpt_at(task, task_order)
        inputs = _names(_role_items(scan, required + optional)[:8])
        has_inputs = bool(inputs)
        analysis_hit = raw.get("id") in allowed_by_analysis
        input_only_hit = has_inputs and _can_activate_from_inputs(raw)
        if not score and not analysis_hit and not input_only_hit:
            continue
        status, blockers = _status_from_policy(raw, scan)
        priority = score * 10 + (20 if analysis_hit else 0) + len(inputs)
        modules.append(
            (
                (task_order, -priority),
                OperationModule(
                    id=raw["id"],
                    title=raw["title"],
                    category=raw.get("category", "未分类"),
                    data_group=raw.get("category", "未分类"),
                    status=status,
                    backend=raw.get("backend") or [],
                    inputs=inputs,
                    steps=raw.get("steps") or [],
                    outputs=raw.get("outputs") or [],
                    checks=raw.get("checks") or [],
                    blockers=blockers,
                    sources=sources,
                    task_order=task_order,
                    task_excerpt=task_excerpt,
                ),
            )
        )

    modules.sort(key=lambda item: item[0])
    return [item for _, item in modules]
