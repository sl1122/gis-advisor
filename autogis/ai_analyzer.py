from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .llm_client import chat_json, get_llm_config


ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = ROOT / ".autogis"
CASE_MEMORY_PATH = MEMORY_DIR / "case_memory.json"


@dataclass
class OperationHint:
    name: str
    reason: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "reason": self.reason, "confidence": self.confidence}


@dataclass
class TaskAnalysis:
    ok: bool
    mode: str
    summary: str
    task_types: list[str] = field(default_factory=list)
    required_data: list[str] = field(default_factory=list)
    operations: list[OperationHint] = field(default_factory=list)
    missing_conditions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    similar_cases: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "summary": self.summary,
            "task_types": self.task_types,
            "required_data": self.required_data,
            "operations": [item.to_dict() for item in self.operations],
            "missing_conditions": self.missing_conditions,
            "risks": self.risks,
            "similar_cases": self.similar_cases,
            "confidence": self.confidence,
        }


RULES = [
    {
        "type": "hydrology",
        "keywords": ["hydrology", "watershed", "stream", "river", "flow", "accumulation", "水文", "流域", "河网", "水系", "流向", "流量", "汇流"],
        "required": ["DEM raster", "optional outlet point", "stream extraction threshold"],
        "operations": ["填洼", "流向", "汇流累积", "河网提取", "流域提取"],
        "risks": ["河网阈值必须结合集水面积和像元大小确认。", "水文分析通常应先填洼再进行流向分析。"],
    },
    {
        "type": "terrain",
        "keywords": ["dem", "slope", "aspect", "hillshade", "illumination", "坡度", "坡向", "山体阴影", "光照", "地形", "高程"],
        "required": ["DEM raster"],
        "operations": ["坡度", "坡向", "山体阴影"],
        "risks": ["连续栅格通常使用拉伸符号系统。"],
    },
    {
        "type": "building_sunlight",
        "keywords": ["sunlight", "sun shadow", "solar", "building shadow", "日照", "建筑日照", "太阳阴影", "背光面", "冬至", "建筑高度"],
        "required": ["building layer", "height field", "candidate points or building centroids", "sun azimuth and altitude"],
        "operations": ["面转栅格", "NoData 赋 0", "坡向", "背光面重分类", "栅格计算器", "阴影/光照栅格", "提取值至点"],
        "risks": [
            "建筑外 NoData 应先转为 0，再做坡向或山体阴影。",
            "背光二值栅格必须乘以真实建筑高度，不能直接用于阴影分析。",
            "后端支持时应开启模型阴影或 3D 阴影选项。",
        ],
    },
    {
        "type": "site_selection",
        "keywords": ["site", "suitability", "buffer", "erase", "select", "选址", "适宜", "缓冲", "擦除", "相交", "按位置", "可视"],
        "required": ["candidate layer", "constraint vector layers", "distance thresholds"],
        "operations": ["缓冲区", "差集/擦除", "相交", "按位置提取", "可视域"],
        "risks": ["距离分析需要投影坐标系。", "差集/擦除的输入顺序必须检查。"],
    },
    {
        "type": "reclass_change",
        "keywords": ["reclass", "change", "transition", "land use", "重分类", "变化", "转移", "土地利用", "图斑", "耕地"],
        "required": ["early raster", "late raster or class raster", "class code table"],
        "operations": ["重分类", "栅格计算器", "变化编码栅格", "转移矩阵"],
        "risks": ["必须检查 NoData 的传递方式。", "图例必须解释每个转移编码。"],
    },
    {
        "type": "zonal_statistics",
        "keywords": ["zonal", "zone", "statistics", "分区统计", "区域统计", "统计", "乡镇", "均值", "总和"],
        "required": ["zone polygon layer", "value raster"],
        "operations": ["分区统计", "统计结果回连分区"],
        "risks": ["分区图层和栅格应具有兼容的坐标系和范围。"],
    },
    {
        "type": "vector_edit_geometry",
        "keywords": ["create feature", "digitize", "move", "translate", "rotate", "split", "cut", "clip", "subdivide", "创建要素", "新增要素", "绘制", "数字化", "移动", "平移", "旋转", "切割", "分割", "划分", "裁剪", "分块"],
        "required": ["target vector layer", "operation parameters", "optional split or overlay layer"],
        "operations": ["创建要素", "平移几何", "旋转要素", "按线分割", "裁剪", "细分"],
        "risks": ["编辑类流程通常需要人工确认几何。", "移动和旋转参数依赖当前坐标系单位和锚点规则。"],
    },
    {
        "type": "remote_sensing",
        "keywords": ["remote sensing", "landsat", "sentinel", "classification", "ndvi", "遥感", "影像", "波段", "分类", "指数", "夜间灯光"],
        "required": ["remote-sensing raster bands", "mask or study area", "optional training samples"],
        "operations": ["波段合成", "按掩膜提取", "指数计算", "分类", "精度评价或变化分析"],
        "risks": ["必须核对波段顺序和 NoData 处理。", "训练样本必须与分类体系一致。"],
    },
]


def _load_cases() -> list[dict[str, Any]]:
    if not CASE_MEMORY_PATH.exists():
        return []
    try:
        data = json.loads(CASE_MEMORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def save_case_memory(case: dict[str, Any]) -> list[dict[str, Any]]:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    cases = _load_cases()
    task = (case.get("task") or "").strip()
    if not task:
        return cases
    cases = [item for item in cases if item.get("task") != task]
    cases.insert(0, case)
    cases = cases[:200]
    CASE_MEMORY_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    return cases


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    words = set(re.findall(r"[a-zA-Z0-9_]+", lowered))
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for size in (2, 3, 4):
            words.update(chunk[i : i + size] for i in range(max(0, len(chunk) - size + 1)))
    return words


def _similar_cases(task: str, limit: int = 5, min_score: float = 0.08) -> list[dict[str, Any]]:
    query = _tokens(task)
    scored: list[tuple[float, dict[str, Any]]] = []
    for case in _load_cases():
        case_tokens = _tokens(case.get("task", ""))
        if not case_tokens:
            continue
        score = len(query & case_tokens) / max(1, len(query | case_tokens))
        if score >= min_score:
            scored.append((score, case))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "score": round(score, 3),
            "task": case.get("task", "")[:300],
            "task_types": case.get("task_types", []),
            "workflow": case.get("workflow", ""),
        }
        for score, case in scored[:limit]
    ]


def analyze_task(task: str, scan: dict[str, Any] | None = None) -> TaskAnalysis:
    task = task.strip()
    scan = scan or {}
    if not task:
        return TaskAnalysis(
            ok=False,
            mode="local_rules",
            summary="No task text was provided.",
            missing_conditions=["Scan a question document or paste task text first."],
        )

    matched_types: list[str] = []
    required_data: list[str] = []
    operations: list[OperationHint] = []
    risks: list[str] = []
    lowered = task.lower()

    for rule in RULES:
        hits = [kw for kw in rule["keywords"] if kw.lower() in lowered]
        if not hits:
            continue
        if rule["type"] == "building_sunlight" and not _has_building_sunlight_context(task):
            continue
        matched_types.append(rule["type"])
        required_data.extend(rule["required"])
        risks.extend(rule["risks"])
        confidence = min(0.95, 0.45 + 0.08 * len(hits))
        operations.extend(
            OperationHint(name=op, reason=f"Matched {rule['type']} keywords: {', '.join(hits[:5])}", confidence=confidence)
            for op in rule["operations"]
        )

    groups = scan.get("groups") or {}
    missing_conditions: list[str] = []
    if "DEM raster" in required_data and not groups.get("dem") and not groups.get("raster"):
        missing_conditions.append("Need DEM/elevation raster, but scan did not identify one.")
    if any("vector" in item or "layer" in item for item in required_data) and not groups.get("vector") and not groups.get("boundary"):
        missing_conditions.append("Need vector layers, but scan did not identify enough vector data.")
    if not matched_types:
        missing_conditions.append("Task type is unclear. Add operation keywords or select a similar remembered case.")

    required_data = sorted(set(required_data))
    risks = sorted(set(risks))
    similar = _similar_cases(task)
    confidence = round(sum(item.confidence for item in operations) / max(1, len(operations)), 3)
    summary = "Local rule analysis only. Treat this as a candidate workflow, not an execution guarantee."
    if similar:
        summary += " Similar cases were found in local memory."

    return TaskAnalysis(
        ok=True,
        mode="local_rules_with_memory",
        summary=summary,
        task_types=matched_types or ["unknown"],
        required_data=required_data,
        operations=operations,
        missing_conditions=missing_conditions,
        risks=risks,
        similar_cases=similar,
        confidence=confidence,
    )


def _has_building_sunlight_context(task: str) -> bool:
    lowered = task.lower()
    explicit_sunlight = any(
        kw in lowered
        for kw in ["日照", "建筑日照", "sunlight", "sun shadow", "solar", "冬至", "太阳阴影", "背光面"]
    )
    building_context = any(kw in lowered for kw in ["建筑", "楼", "高度", "building", "height"])
    shadow_context = lowered.replace("山体阴影", "").replace("hillshade", "")
    return explicit_sunlight or (building_context and any(kw in shadow_context for kw in ["阴影", "shadow", "太阳", "sun"]))


def analyze_task_with_llm(
    task: str,
    scan: dict[str, Any] | None = None,
    provider: str = "deepseek",
    model: str | None = None,
) -> dict[str, Any]:
    local = analyze_task(task, scan=scan).to_dict()
    config = get_llm_config(provider, model)
    if not config.has_key:
        local["llm"] = {
            "used": False,
            "provider": provider,
            "error": f"Missing API key environment variable: {config.api_key_env}",
        }
        return local

    scan_summary = {
        "counts": (scan or {}).get("counts", {}),
        "suggested": (scan or {}).get("suggested", {}),
        "groups": {
            key: [
                {
                    "name": item.get("name"),
                    "role": item.get("role"),
                    "kind": item.get("kind"),
                    "path": item.get("path"),
                    "reason": item.get("reason"),
                }
                for item in items[:10]
            ]
            for key, items in ((scan or {}).get("groups") or {}).items()
        },
    }
    system = (
        "You are a GIS workflow analyst. Return strict JSON only. "
        "Analyze the task and scanned files. Do not invent data that is not present. "
        "Pay special attention to Chinese formulas and calculation relationships extracted from PDFs. "
        "Convert each relevant formula into GIS data requirements, field requirements, calculation steps, and result checks. "
        "If data or parameters are missing, list them explicitly. "
        "Prefer conservative workflows that require user confirmation before execution."
    )
    user = json.dumps(
        {
            "task": task,
            "scan_summary": scan_summary,
            "local_rule_analysis": local,
            "expected_schema": {
                "task_types": ["string"],
                "required_data_slots": [{"slot": "string", "reason": "string", "required": True}],
                "candidate_operations": [{"name": "string", "reason": "string", "confidence": 0.0}],
                "missing_conditions": ["string"],
                "risks": ["string"],
                "questions_for_user": ["string"],
                "formula_interpretation": [
                    {
                        "formula": "string",
                        "meaning": "string",
                        "needed_fields": ["string"],
                        "gis_steps": ["string"],
                        "checks": ["string"],
                    }
                ],
                "workflow_outline": [{"group": "string", "steps": ["string"]}],
                "confidence": 0.0,
            },
        },
        ensure_ascii=False,
    )
    try:
        llm = chat_json(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            provider=provider,
            model=model,
        )
        local["llm"] = {
            "used": True,
            "provider": provider,
            "model": config.model,
            "analysis": llm,
        }
        local["mode"] = f"local_rules_with_{provider}"
        return local
    except Exception as exc:
        local["llm"] = {
            "used": False,
            "provider": provider,
            "model": config.model,
            "error": str(exc),
        }
        return local
