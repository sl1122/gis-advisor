from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CASE_MEMORY_PATH = ROOT / ".autogis" / "case_memory.json"


@dataclass
class SoftwareRoute:
    arcgis_pro: str
    qgis: str
    parameters: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    automation: str = "仅提供指导"

    def to_dict(self) -> dict[str, Any]:
        return {
            "arcgis_pro": self.arcgis_pro,
            "qgis": self.qgis,
            "parameters": self.parameters,
            "checks": self.checks,
            "automation": self.automation,
        }


@dataclass
class GuidanceStep:
    title: str
    purpose: str
    reason: str
    route: SoftwareRoute
    risk: str = ""
    user_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "purpose": self.purpose,
            "reason": self.reason,
            "route": self.route.to_dict(),
            "risk": self.risk,
            "user_action": self.user_action,
        }


@dataclass
class GuidanceReport:
    orientation: str
    task_category: str
    analysis_mode: str
    goal: str
    evidence: list[str]
    data_roles: list[str]
    missing_or_uncertain: list[str]
    recommended_route: list[GuidanceStep]
    result_checks: list[str]
    similar_memory: list[dict[str, Any]]
    execution_policy: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "orientation": self.orientation,
            "task_category": self.task_category,
            "analysis_mode": self.analysis_mode,
            "goal": self.goal,
            "evidence": self.evidence,
            "data_roles": self.data_roles,
            "missing_or_uncertain": self.missing_or_uncertain,
            "recommended_route": [step.to_dict() for step in self.recommended_route],
            "result_checks": self.result_checks,
            "similar_memory": self.similar_memory,
            "execution_policy": self.execution_policy,
        }


def _contains_any(text: str, words: list[str]) -> bool:
    lowered = text.lower()
    return any(word.lower() in lowered for word in words)


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    tokens = set(re.findall(r"[a-zA-Z0-9_]+", lowered))
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for size in (2, 3, 4):
            tokens.update(chunk[i : i + size] for i in range(max(0, len(chunk) - size + 1)))
    return tokens


def _case_memory(task: str, limit: int = 4, min_score: float = 0.08) -> list[dict[str, Any]]:
    if not CASE_MEMORY_PATH.exists():
        return []
    try:
        cases = json.loads(CASE_MEMORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    query = _tokens(task)
    scored: list[tuple[float, dict[str, Any]]] = []
    for case in cases if isinstance(cases, list) else []:
        case_task = case.get("task", "")
        case_tokens = _tokens(case_task)
        if not case_tokens:
            continue
        score = len(query & case_tokens) / max(1, len(query | case_tokens))
        if score >= min_score:
            scored.append((score, case))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "score": round(score, 3),
            "task": case.get("task", "")[:180],
            "task_types": case.get("task_types", []),
            "usable": "可作为相似案例参考，仍需核对本题数据和参数。",
        }
        for score, case in scored[:limit]
    ]


def _scan_roles(scan: dict[str, Any]) -> list[str]:
    groups = scan.get("groups") or {}
    labels = {
        "question": "题目文档",
        "dem": "DEM 高程数据",
        "boundary": "研究区边界",
        "raster": "栅格数据",
        "remote_sensing": "遥感影像",
        "vector": "矢量数据",
        "hydro_vector": "水系矢量",
        "table": "表格数据",
        "document": "说明文档",
    }
    roles: list[str] = []
    for key, label in labels.items():
        items = groups.get(key) or []
        if items:
            roles.append(f"{label}：{len(items)} 个")
    return roles


def _base_checks() -> list[str]:
    return [
        "距离、面积、缓冲和可视域分析前，确认数据使用米制投影坐标系。",
        "每次叠加、裁剪、擦除、融合后，重新计算面积或长度字段。",
        "打开属性表检查关键字段是否存在，避免把 Id、Code、Value 等字段误当成题目含义。",
        "最终图件检查图名、图例、比例尺、指北针、单位和分类说明是否齐全。",
    ]


def _hydrology_steps() -> list[GuidanceStep]:
    return [
        GuidanceStep(
            title="填洼",
            purpose="修正 DEM 中会影响水流路径的局部洼地。",
            reason="题目出现河网、流向、汇流累积时，水文流程通常先从填洼开始。",
            route=SoftwareRoute(
                arcgis_pro="空间分析工具 > 水文分析 > 填洼（Fill）",
                qgis="处理工具箱 > 水文分析/WhiteboxTools > 填洼（Fill sinks）",
                parameters=["输入 DEM", "输出填洼 DEM"],
                checks=["填洼输出应保持原 DEM 的像元大小和投影。"],
                automation="可自动执行：QGIS/Whitebox 路线",
            ),
        ),
        GuidanceStep(
            title="流向与汇流累积",
            purpose="计算每个像元的水流方向和上游贡献像元数。",
            reason="河网提取、集水面积换算、流域划分都依赖汇流累积结果。",
            route=SoftwareRoute(
                arcgis_pro="空间分析工具 > 水文分析 > 流向（Flow Direction）/ 汇流累积（Flow Accumulation）",
                qgis="处理工具箱 > WhiteboxTools > D8 汇流累积（D8 Flow Accumulation）",
                parameters=["填洼 DEM", "输出类型通常选 cells"],
                checks=["阈值对应集水面积 = 阈值 × 像元面积。"],
                automation="可自动执行：WhiteboxTools",
            ),
        ),
        GuidanceStep(
            title="阈值提取河网",
            purpose="用汇流累积阈值提取河网栅格。",
            reason="题目给出阈值时，应把汇流累积大于等于阈值的像元作为河网。",
            route=SoftwareRoute(
                arcgis_pro="空间分析工具 > 地图代数 > 栅格计算器（Raster Calculator）",
                qgis="处理工具箱 > GDAL > 栅格计算器（Raster calculator）",
                parameters=["公式示例：FlowAccumulation >= 500"],
                checks=["河网应沿低谷分布，像元数和题目要求应能追溯。"],
                automation="可自动执行：QGIS/GDAL 路线",
            ),
        ),
    ]


def _site_steps() -> list[GuidanceStep]:
    return [
        GuidanceStep(
            title="约束条件识别",
            purpose="区分禁止建设区、候选区和评价因子。",
            reason="模糊选址题不能直接做缓冲叠加，必须先判断题目是约束排除还是多因子评价。",
            route=SoftwareRoute(
                arcgis_pro="先在内容列表和属性表中核对各约束图层",
                qgis="先在图层面板和属性表中核对各约束图层",
                parameters=["约束图层", "候选区图层", "距离阈值", "面积阈值"],
                checks=["权重未给出时，不能伪造多因子加权评价。"],
                automation="仅提供指导",
            ),
            risk="题目没有明确权重时，应优先给约束排除路线，并把加权评价标为备选方案。",
        ),
        GuidanceStep(
            title="缓冲与擦除",
            purpose="从候选区中排除不适宜区域。",
            reason="题目出现“距离某对象 X 米内不适宜”时，通常先缓冲，再擦除。",
            route=SoftwareRoute(
                arcgis_pro="分析 > 工具 > 邻近分析 > 缓冲区（Buffer）；分析 > 工具 > 叠加分析 > 擦除（Erase）",
                qgis="处理工具箱 > 矢量几何 > 缓冲区（Buffer）；处理工具箱 > 矢量叠加 > 差集（Difference）",
                parameters=["输入要素", "缓冲距离", "是否融合", "擦除输入和擦除要素"],
                checks=["擦除顺序不能反；缓冲距离单位应为米。"],
                automation="可选自动执行：参数明确时",
            ),
        ),
        GuidanceStep(
            title="候选区筛选与制图",
            purpose="按面积、位置、可视性或属性条件筛选候选结果。",
            reason="竞赛题通常不仅要结果，还要专题图和可解释过程。",
            route=SoftwareRoute(
                arcgis_pro="分析 > 工具 > 提取分析 > 按属性选择/按位置选择；布局视图中制图",
                qgis="处理工具箱 > 矢量选择；布局管理器中制图",
                parameters=["面积字段", "筛选表达式", "图例分类", "标注字段"],
                checks=["筛选后检查属性表记录数、面积总和和图件表达。"],
                automation="半自动：筛选可执行，制图需人工确认",
            ),
        ),
    ]


def _viewshed_steps() -> list[GuidanceStep]:
    return [
        GuidanceStep(
            title="确认观察点与观察高度",
            purpose="确定视域分析的观察点、观察高度和分析半径。",
            reason="可视域工具对观察点和高度参数敏感，观察高度不是 DEM 绝对高程。",
            route=SoftwareRoute(
                arcgis_pro="空间分析工具 > 表面分析 > 可视域（Viewshed）或可视域 2（Viewshed 2）",
                qgis="处理工具箱 > GDAL > 可视域（Viewshed）",
                parameters=["DEM", "观察点", "观察高度", "目标高度", "最大距离"],
                checks=["确认观察高度字段或参数填的是相对地面高度，例如 10 m。"],
                automation="单点可自动执行；多候选点需批处理模块",
            ),
            risk="多个候选点不能直接当成一个单点参数，需要循环计算并统计可视面积。",
        ),
        GuidanceStep(
            title="统计可视面积并排序",
            purpose="比较候选点覆盖范围，选择可视面积最大的点。",
            reason="瞭望塔选址类题通常以可视面积或覆盖范围作为优选依据。",
            route=SoftwareRoute(
                arcgis_pro="空间分析工具 > 分区分析/栅格属性统计，或转面后计算面积",
                qgis="栅格像元统计或栅格转矢量后计算面积",
                parameters=["可视域栅格", "可见值编码", "像元面积"],
                checks=["确认可见值和不可见值的编码，不要把 NoData 当成不可见。"],
                automation="半自动：需要确认输出编码后再统计",
            ),
        ),
    ]


def _zonal_steps() -> list[GuidanceStep]:
    return [
        GuidanceStep(
            title="分区统计",
            purpose="按行政区、乡镇或研究单元统计栅格指标。",
            reason="题目出现乡镇、区域均值、总和、夜间灯光、GDP 分配时，通常需要分区统计和字段回连。",
            route=SoftwareRoute(
                arcgis_pro="空间分析工具 > 分区分析 > 以表格显示分区统计（Zonal Statistics as Table）",
                qgis="处理工具箱 > 栅格分析 > 分区统计（Zonal statistics）",
                parameters=["分区面", "分区字段", "值栅格", "统计类型"],
                checks=["统计表回连后检查 Null，确认分区字段唯一且类型一致。"],
                automation="可选自动执行：字段明确时",
            ),
        ),
        GuidanceStep(
            title="指标回连与专题图",
            purpose="把统计结果回连到分区面并进行分类表达。",
            reason="科研和竞赛题通常需要空间分布图，而不是只要统计表。",
            route=SoftwareRoute(
                arcgis_pro="数据管理工具 > 连接字段（Join Field）；符号系统中分级设色",
                qgis="属性表连接或按字段连接；图层样式中分级渲染",
                parameters=["连接字段", "统计字段", "分级方法", "颜色方案"],
                checks=["检查未匹配记录、异常值和图例单位。"],
                automation="指导为主",
            ),
        ),
    ]


def _terrain_steps() -> list[GuidanceStep]:
    return [
        GuidanceStep(
            title="坡度、坡向、山体阴影",
            purpose="从 DEM 生成基础地形因子和制图底图。",
            reason="题目出现坡度、坡向、地形复杂度或山体阴影时，这是基础处理链。",
            route=SoftwareRoute(
                arcgis_pro="空间分析工具 > 表面分析 > 坡度（Slope）/ 坡向（Aspect）/ 山体阴影（Hillshade）",
                qgis="处理工具箱 > GDAL > 坡度/坡向/山体阴影",
                parameters=["DEM", "Z 因子", "坡度单位", "光照方位角和高度角"],
                checks=["坡度单位要确认是度还是百分比；连续栅格用拉伸渲染。"],
                automation="可自动执行：QGIS/GDAL 路线",
            ),
        )
    ]


def _sunlight_steps() -> list[GuidanceStep]:
    return [
        GuidanceStep(
            title="建筑高度面构建",
            purpose="把建筑面转换为用于日照或阴影判断的高度栅格。",
            reason="日照题不能只看平面建筑，必须有高度字段或楼层数换算。",
            route=SoftwareRoute(
                arcgis_pro="转换工具 > 转为栅格 > 面转栅格（Polygon to Raster）",
                qgis="处理工具箱 > GDAL > 栅格化（Rasterize）",
                parameters=["建筑面", "高度字段", "像元大小", "NoData 处理"],
                checks=["若只有楼层数字段，先新增高度字段：楼层数 × 层高。"],
                automation="半自动：字段明确时可执行",
            ),
            risk="没有真实高度字段时不能直接运行日照链。",
        ),
        GuidanceStep(
            title="日照/阴影方法选择",
            purpose="区分 2D 光照栅格、山体阴影和真实 3D 太阳阴影体。",
            reason="QGIS Hillshade 不等价于 ArcGIS Pro 的 3D Sun Shadow Volume。",
            route=SoftwareRoute(
                arcgis_pro="3D Analyst > Sun Shadow Volume；或空间分析工具中的 Hillshade 作为光照表达",
                qgis="原生山体阴影（Hillshade）或插件/3D 后端",
                parameters=["太阳方位角", "太阳高度角", "日期时间", "建筑高度"],
                checks=["题目要求 3D 投影阴影时，不能用普通 Hillshade 冒充。"],
                automation="指导为主",
            ),
        ),
    ]


def _remote_steps() -> list[GuidanceStep]:
    return [
        GuidanceStep(
            title="遥感指数、分类或变化检测",
            purpose="根据波段、样本和研究区生成遥感分析结果。",
            reason="遥感题的关键不是先跑算法，而是确认波段含义、样本体系和精度评价方法。",
            route=SoftwareRoute(
                arcgis_pro="影像分析/栅格函数；Image Analyst 或 Spatial Analyst 工具箱",
                qgis="处理工具箱 > GDAL/Orfeo Toolbox；栅格计算器和分类工具",
                parameters=["波段顺序", "研究区掩膜", "指数公式", "训练样本", "分类体系"],
                checks=["波段顺序必须确认；离散分类结果用分类符号系统。"],
                automation="部分自动：指数计算和裁剪可执行，分类需人工确认样本",
            ),
        )
    ]


def build_guidance(task: str, scan: dict[str, Any] | None = None) -> GuidanceReport:
    task = task.strip()
    scan = scan or {}
    evidence: list[str] = []
    steps: list[GuidanceStep] = []
    categories: list[str] = []
    missing: list[str] = []

    if _contains_any(task, ["国赛", "竞赛", "试题", "空", "图", "答卷"]):
        orientation = "竞赛/作业导向"
    elif _contains_any(task, ["论文", "科研", "项目", "指标", "评价", "模型"]):
        orientation = "科研/项目导向"
    else:
        orientation = "通用 GIS 需求导向"

    if _contains_any(task, ["水文", "填洼", "流向", "流量", "汇流", "河网", "watershed", "flow accumulation"]):
        categories.append("水文分析")
        evidence.append("题目包含水文、填洼、流向、汇流或河网等关键词。")
        steps.extend(_hydrology_steps())
    if _contains_any(task, ["选址", "适宜", "缓冲", "擦除", "相交", "候选区", "suitability", "site"]):
        categories.append("选址/约束筛选")
        evidence.append("题目包含选址、适宜性、缓冲、擦除或候选区等关键词。")
        steps.extend(_site_steps())
    if _contains_any(task, ["可视域", "视域", "可视", "观察点", "瞭望塔", "viewshed"]):
        categories.append("可视域分析")
        evidence.append("题目包含可视域、观察点或瞭望塔等关键词。")
        steps.extend(_viewshed_steps())
    if _contains_any(task, ["分区统计", "区域统计", "乡镇", "GDP", "夜间灯光", "均值", "总和"]):
        categories.append("分区统计/指标回连")
        evidence.append("题目包含分区统计、乡镇、GDP、夜间灯光或统计指标。")
        steps.extend(_zonal_steps())
    if _contains_any(task, ["空地率", "TCI", "地形复杂度", "LSI", "耕地规模化", "夜间灯光", "权重", "汇流累积量阈值"]):
        categories.append("公式/指标计算")
        evidence.append("题面包含公式、阈值或指标定义，需要先把公式翻译成字段和 GIS 计算链。")
        steps.extend(_formula_steps(task))
    if _contains_any(task, ["坡度", "坡向", "山体阴影", "地形", "DEM", "hillshade", "slope", "aspect"]):
        categories.append("地形分析")
        evidence.append("题目包含 DEM、坡度、坡向、地形或山体阴影。")
        steps.extend(_terrain_steps())
    if _is_building_sunlight_question(task):
        categories.append("建筑日照/阴影分析")
        evidence.append("题目包含建筑日照、太阳角、冬至、背光面或建筑高度语境。")
        steps.extend(_sunlight_steps())
    if _contains_any(task, ["遥感", "影像", "波段", "NDVI", "分类", "变化检测", "Landsat", "Sentinel"]):
        categories.append("遥感处理")
        evidence.append("题目包含遥感影像、波段、指数、分类或变化检测。")
        steps.extend(_remote_steps())

    roles = _scan_roles(scan)
    groups = scan.get("groups") or {}
    if "水文分析" in categories and not groups.get("dem"):
        missing.append("水文分析需要 DEM，高程数据未在扫描结果中明确识别。")
    if "建筑日照/阴影分析" in categories:
        missing.append("需要确认建筑高度字段；若只有楼层数字段，应先换算为高度字段。")
    if "选址/约束筛选" in categories:
        missing.append("需要确认哪些图层是约束区，哪些图层是候选区；擦除顺序不能反。")
    if "可视域分析" in categories:
        missing.append("需要确认观察点、观察高度、目标高度和分析半径；多点可视域需要批处理。")
    if not categories:
        categories.append("未明确分类")
        missing.append("题目关键词不足，建议补充目标、数据类型、成果要求或相似训练案例。")

    goal = "拆解题目或项目需求，给出 ArcGIS Pro 优先、QGIS 免费替代的操作路线。"
    result_checks = _base_checks()
    if "水文分析" in categories:
        result_checks.append("河网提取结果应沿低谷分布，并能解释阈值与集水面积的换算关系。")
    if "可视域分析" in categories:
        result_checks.append("可视域结果需确认可见值编码、不可见值编码和 NoData 含义。")
    if "分区统计/指标回连" in categories:
        result_checks.append("分区统计回连后检查 Null 值、异常值和字段类型。")

    return GuidanceReport(
        orientation=orientation,
        task_category=" / ".join(categories),
        analysis_mode="题目分析优先；自动执行仅作为确定性步骤的辅助。",
        goal=goal,
        evidence=evidence,
        data_roles=roles,
        missing_or_uncertain=missing,
        recommended_route=steps,
        result_checks=result_checks,
        similar_memory=_case_memory(task),
        execution_policy="默认不承诺一键得出正确结果；仅对参数明确、风险低的步骤提供可选自动执行。",
    )


def _is_building_sunlight_question(text: str) -> bool:
    lowered = text.lower()
    explicit_terms = ["日照", "建筑日照", "太阳阴影", "背光", "冬至", "sun shadow", "sunlight", "solar"]
    if _contains_any(text, explicit_terms):
        return True
    shadow_context = lowered.replace("山体阴影", "").replace("hillshade", "")
    has_building = any(term in lowered for term in ["建筑", "楼", "高度", "building", "height"])
    has_shadow = any(term in shadow_context for term in ["阴影", "shadow", "太阳", "sun"])
    return has_building and has_shadow


def _formula_steps(task: str) -> list[GuidanceStep]:
    steps: list[GuidanceStep] = []
    if _contains_any(task, ["空地率"]):
        steps.append(
            GuidanceStep(
                title="空地率计算",
                purpose="计算片区内未被建筑物覆盖的用地面积占片区总面积的比例。",
                reason="题目给出空地率定义，应转成片区面积、建筑覆盖面积和字段计算。",
                route=SoftwareRoute(
                    arcgis_pro="分析 > 工具 > 擦除/相交；数据管理工具 > 计算几何属性；属性表 > 字段计算器",
                    qgis="处理工具箱 > 叠加分析 > 差集/相交；属性表 > 字段计算器",
                    parameters=["片区面", "建筑物面", "片区编号字段", "面积字段单位"],
                    checks=["确认建筑物面已合并或按片区统计；空地率通常为 (片区面积 - 建筑覆盖面积) / 片区面积。"],
                    automation="可半自动：面积统计需确认片区字段",
                ),
            )
        )
    if _contains_any(task, ["TCI", "地形复杂度"]):
        steps.append(
            GuidanceStep(
                title="TCI 地形复杂度指数",
                purpose="按公式把高程起伏因子和坡度因子合成为像元级 TCI，再按乡镇求均值。",
                reason="TCI 是栅格公式，不应直接在属性表里手填。",
                route=SoftwareRoute(
                    arcgis_pro="空间分析工具 > 邻域分析 > 焦点统计；表面分析 > 坡度；地图代数 > 栅格计算器；分区统计为表",
                    qgis="处理工具箱 > 栅格地形分析/邻域统计；栅格计算器；分区统计",
                    parameters=["DEM", "邻域窗口", "坡度栅格 S", "高程起伏 R", "乡镇边界"],
                    checks=["确认 Ln 使用自然对数；R、S 的单位和 NoData 处理要一致；乡镇 TCI 是像元均值。"],
                    automation="可自动执行：公式和窗口参数明确后",
                ),
            )
        )
    if _contains_any(task, ["LSI", "耕地规模化"]):
        steps.append(
            GuidanceStep(
                title="LSI 耕地规模化指数",
                purpose="按乡镇统计耕地总面积和满足面积阈值的耕地图斑数量，再代入公式。",
                reason="公式中的 A 和 N 分别来自面积汇总和斑块计数，不能只看图层总面积。",
                route=SoftwareRoute(
                    arcgis_pro="分析 > 工具 > 按属性选择图层；多部件至单部件；汇总统计；连接字段；字段计算器",
                    qgis="按表达式选择；多部件转单部件；按位置连接/统计；字段计算器",
                    parameters=["耕地图斑", "乡镇边界", "面积阈值", "乡镇编号字段"],
                    checks=["先剔除小于阈值的斑块再计数；面积单位统一为题目要求的 km² 或 m²。"],
                    automation="可半自动：需确认耕地编码和面积阈值",
                ),
            )
        )
    if _contains_any(task, ["夜间灯光", "GDP", "权重"]):
        steps.append(
            GuidanceStep(
                title="夜间灯光加权 GDP 分配",
                purpose="用乡镇夜间灯光占区县灯光总量的比例，把区县 GDP 分配到乡镇。",
                reason="这是权重分配问题，核心是同一区县内部的灯光权重归一化。",
                route=SoftwareRoute(
                    arcgis_pro="空间分析工具 > 分区统计为表；连接字段；字段计算器",
                    qgis="栅格分析 > 分区统计；属性连接；字段计算器",
                    parameters=["夜间灯光栅格", "乡镇边界", "区县 GDP 表", "区县代码", "乡镇代码"],
                    checks=["每个区县内乡镇权重之和应约等于 1；灯光 NoData 和 0 值要区分。"],
                    automation="可半自动：字段映射确认后",
                ),
            )
        )
    if _contains_any(task, ["汇流累积量阈值", "阈值>500", "阈值 > 500"]):
        steps.append(
            GuidanceStep(
                title="汇流阈值与集水面积换算",
                purpose="把 flow accumulation 的像元数量阈值换算为真实上游集水面积。",
                reason="汇流累积量通常表示上游像元数，必须乘以像元面积。",
                route=SoftwareRoute(
                    arcgis_pro="空间分析工具 > 水文分析 > 汇流累积；地图代数 > 栅格计算器",
                    qgis="处理工具箱 > GRASS/Whitebox/GDAL 水文工具；栅格计算器",
                    parameters=["流量累积栅格", "阈值", "像元宽度", "像元高度", "面积单位换算"],
                    checks=["集水面积 = 阈值 × 像元宽度 × 像元高度；若输出 km²，需要除以 1,000,000。"],
                    automation="可自动执行：像元大小明确后",
                ),
            )
        )
    return steps
