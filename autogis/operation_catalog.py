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
    normalized = " ".join(text.replace("\r", "\n").split())
    if not normalized:
        return ""
    keyword_pos = min(index, len(normalized) - 1)
    start_candidates = [normalized.rfind(mark, 0, keyword_pos) for mark in ["。", "；", ";", "\n"]]
    end_candidates = [normalized.find(mark, keyword_pos) for mark in ["。", "；", ";", "\n"]]
    start = max(start_candidates)
    start = 0 if start < 0 else start + 1
    valid_ends = [item for item in end_candidates if item >= 0]
    end = min(valid_ends) + 1 if valid_ends else min(len(normalized), keyword_pos + radius)
    snippet = normalized[start:end].strip()
    if len(snippet) > radius:
        local_start = max(0, keyword_pos - start - radius // 2)
        snippet = snippet[local_start : local_start + radius].strip()
        if local_start > 0:
            snippet = f"...{snippet}"
        if start + local_start + radius < end:
            snippet = f"{snippet}..."
    return snippet


def _matched_any(task: str, words: list[str]) -> bool:
    lowered = task.lower()
    return any(word.lower() in lowered for word in words)


def _customize_vector_edit_module(raw: dict[str, Any], task: str) -> dict[str, Any]:
    operations = [
        {
            "name": "创建/数字化要素",
            "words": ["create feature", "digitize", "new feature", "新增要素", "创建要素", "绘制", "数字化", "新建"],
            "steps": ["确认目标图层、几何类型和必填字段", "按题目给定坐标或构造规则创建要素", "检查几何位置、捕捉和属性完整性"],
            "outputs": ["created_features.gpkg"],
            "blockers": ["创建要素需要明确坐标、草图或构造规则；否则只能给操作指导。"],
        },
        {
            "name": "移动/平移要素",
            "words": ["move", "translate", "移动", "平移", "偏移"],
            "steps": ["确认目标图层和要移动的要素", "填写 X/Y 偏移量并执行移动/平移", "检查移动后位置、坐标单位和属性继承"],
            "outputs": ["translated_features.gpkg"],
            "blockers": ["移动前必须确认 X/Y 偏移量和当前坐标系单位。"],
        },
        {
            "name": "旋转要素",
            "words": ["rotate", "旋转", "转动"],
            "steps": ["确认目标图层、旋转角度和旋转中心", "执行旋转要素", "检查角度方向和位置偏差"],
            "outputs": ["rotated_features.gpkg"],
            "blockers": ["旋转必须确认角度方向和旋转中心。"],
        },
        {
            "name": "按线切割要素",
            "words": ["split", "cut", "切割", "分割", "切分"],
            "steps": ["确认目标图层和切割线图层", "执行按线分割", "检查分割结果、面积和属性继承"],
            "outputs": ["split_features.gpkg"],
            "blockers": ["切割线必须真正穿过目标要素。"],
        },
        {
            "name": "裁剪矢量图层",
            "words": ["clip", "裁剪", "按范围", "掩膜"],
            "steps": ["确认目标图层和裁剪边界", "执行裁剪", "检查裁剪范围、面积和字段保留情况"],
            "outputs": ["clipped_features.gpkg"],
            "blockers": ["需要确认题目要求的是裁剪、相交还是擦除。"],
        },
        {
            "name": "细分/分块要素",
            "words": ["subdivide", "partition", "网格", "鱼网", "分块"],
            "steps": ["确认是否需要技术性细分或规则网格", "执行细分/分块", "检查节点数、面积和拓扑"],
            "outputs": ["subdivided_features.gpkg"],
            "blockers": ["细分参数和分块规则需要确认。"],
        },
    ]
    matched = [item for item in operations if _matched_any(task, item["words"])]
    if not matched:
        return raw
    tailored = dict(raw)
    names = [item["name"] for item in matched]
    tailored["title"] = "、".join(names)
    tailored["steps"] = [step for item in matched for step in item["steps"]]
    tailored["outputs"] = [output for item in matched for output in item["outputs"]]
    tailored["blockers"] = [blocker for item in matched for blocker in item["blockers"]]
    tailored["checks"] = ["只显示题目命中的编辑操作；未命中的创建、旋转、切割、划分等不会作为本题流程。", "编辑类任务执行前必须确认坐标系、捕捉和属性继承。"]
    return tailored


def _customize_module(raw: dict[str, Any], task: str) -> dict[str, Any]:
    if raw.get("id") == "vector_edit_geometry":
        return _customize_vector_edit_module(raw, task)
    return raw


def _is_vector_overlay_context(task: str) -> bool:
    lowered = task.lower()
    direct = ["缓冲", "擦除", "相交", "叠置", "约束", "候选区", "适宜", "最小距离", "距离筛选", "buffer", "erase", "intersect", "overlay"]
    if any(word.lower() in lowered for word in direct):
        return True
    has_road = any(word in lowered for word in ["道路", "路网", "road"])
    has_constraint = any(word in lowered for word in ["噪声", "影响距离", "不适宜", "建设适宜", "退让"])
    return has_road and has_constraint


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
        "remote_sensing_otb": ["遥感", "remote sensing", "landsat", "sentinel", "modis", "ndvi", "ndwi", "波段", "监督分类", "精度评价", "变化检测"],
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

    for source_raw in library.get("modules", []):
        raw = _customize_module(source_raw, task)
        keywords = raw.get("keywords") or []
        required = raw.get("input_roles") or []
        optional = raw.get("optional_roles") or []
        score = _keyword_score(task, keywords)
        if raw.get("id") == "vector_overlay_area" and score and not _is_vector_overlay_context(task):
            score = 0
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
