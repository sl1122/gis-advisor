from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .workflow import Workflow, WorkflowStep


def _contains_any(text: str, words: list[str]) -> bool:
    lowered = text.lower()
    return any(word.lower() in lowered for word in words)


def _first_keyword_index(text: str, words: list[str]) -> int:
    lowered = text.lower()
    indexes = [lowered.find(word.lower()) for word in words if word.lower() in lowered]
    return min(indexes) if indexes else 999999


def _is_building_sunlight_task(text: str) -> bool:
    lowered = text.lower()
    explicit_terms = ["sunlight", "sun shadow", "solar", "solar radiation", "building sunlight", "日照", "建筑日照", "太阳阴影", "背光面", "冬至"]
    if _contains_any(text, explicit_terms):
        return True
    has_building = any(term in lowered for term in ["建筑", "楼", "高度", "building", "height"])
    shadow_context = lowered.replace("山体阴影", "").replace("hillshade", "")
    has_shadow = any(term in shadow_context for term in ["阴影", "shadow", "太阳", "sun"])
    return has_building and has_shadow


def _is_road_distance_overlay_task(text: str) -> bool:
    lowered = text.lower()
    has_road = any(term in lowered for term in ["道路", "路网", "road"])
    has_distance_filter = any(term in lowered for term in ["距离", "噪声", "影响", "最小距离", "小于", "≤", "<=", "buffer"])
    has_target = any(term in lowered for term in ["建筑", "候选", "要素", "building", "feature"])
    return has_road and has_distance_filter and has_target


def _is_site_selection_context(text: str) -> bool:
    lowered = text.lower()
    direct = ["site", "suitability", "buffer", "erase", "intersect", "select by location", "service area", "选址", "适宜", "缓冲", "擦除", "相交", "按位置", "候选区"]
    if any(word.lower() in lowered for word in direct):
        return True
    return _is_road_distance_overlay_task(text)


def _data_check_step() -> WorkflowStep:
    return WorkflowStep(
        id="00_data_check",
        title="数据检查",
        purpose="处理前检查坐标系、范围、字段、像元大小、NoData 和输出路径。",
        engine="autogis",
        algorithm="inspect",
        checks=[
            "距离和面积分析前确认使用投影坐标系。",
            "栅格分析前确认像元大小、NoData、范围和掩膜。",
            "输出路径避免过长，结果文件名尽量简洁。",
        ],
    )


def _hydrology_steps() -> list[WorkflowStep]:
    return [
        WorkflowStep(
            id="10_fill_sinks",
            title="填洼",
            purpose="生成水文校正后的 DEM，并输出基础流向栅格。",
            engine="qgis_processing",
            algorithm="native:fillsinkswangliu",
            inputs={"INPUT": "<DEM>"},
            parameters={"BAND": 1, "MIN_SLOPE": 0.1},
            outputs={
                "OUTPUT_FILLED_DEM": "filled_dem.tif",
                "OUTPUT_FLOW_DIRECTIONS": "flow_direction.tif",
            },
            checks=["水文分析通常先填洼，再进行流向和汇流累积。"],
        ),
        WorkflowStep(
            id="11_flow_accumulation",
            title="汇流累积",
            purpose="计算每个像元上游汇入的像元数量。",
            engine="whitebox",
            algorithm="D8FlowAccumulation",
            inputs={"input": "filled_dem.tif"},
            parameters={"out_type": "cells"},
            outputs={"output": "flow_accumulation.tif"},
            checks=["使用填洼后的 DEM 计算汇流累积，后续河网提取才能自动衔接。"],
        ),
        WorkflowStep(
            id="12_stream_extract",
            title="河网提取",
            purpose="使用确认后的汇流累积阈值提取河网栅格。",
            engine="qgis_processing",
            algorithm="gdal:rastercalculator",
            inputs={"INPUT_A": "flow_accumulation.tif"},
            parameters={"BAND_A": 1, "FORMULA": "A >= threshold"},
            outputs={"OUTPUT": "stream_network.tif"},
            checks=["阈值应根据目标集水面积和栅格像元面积确认。"],
        ),
    ]


def _terrain_steps() -> list[WorkflowStep]:
    return [
        WorkflowStep(
            id="20_slope",
            title="坡度",
            purpose="由 DEM 计算坡度栅格。",
            engine="qgis_processing",
            algorithm="gdal:slope",
            inputs={"INPUT": "<DEM>"},
            parameters={"BAND": 1, "SCALE": 1},
            outputs={"OUTPUT": "slope.tif"},
        ),
        WorkflowStep(
            id="21_aspect",
            title="坡向",
            purpose="由 DEM 计算坡向栅格。",
            engine="qgis_processing",
            algorithm="gdal:aspect",
            inputs={"INPUT": "<DEM>"},
            parameters={"BAND": 1},
            outputs={"OUTPUT": "aspect.tif"},
        ),
        WorkflowStep(
            id="22_hillshade",
            title="山体阴影",
            purpose="由 DEM 生成山体阴影或光照表达底图。",
            engine="qgis_processing",
            algorithm="gdal:hillshade",
            inputs={"INPUT": "<DEM>"},
            parameters={"BAND": 1, "Z_FACTOR": 1, "SCALE": 1, "AZIMUTH": 315, "ALTITUDE": 45},
            outputs={"OUTPUT": "hillshade.tif"},
            checks=["山体阴影通常使用灰度拉伸符号系统。"],
        ),
    ]


def _sunlight_analysis_steps() -> list[WorkflowStep]:
    return [
        WorkflowStep(
            id="26_building_height_raster",
            title="建筑高度栅格",
            purpose="把建筑面按高度字段栅格化，形成日照/阴影分析所需的高度表面。",
            engine="qgis_processing",
            algorithm="gdal:rasterize",
            inputs={"INPUT": "<BUILDING_LAYER>"},
            parameters={
                "FIELD": "<HEIGHT_FIELD>",
                "BURN": 0,
                "UNITS": 1,
                "WIDTH": "<CELL_SIZE>",
                "HEIGHT": "<CELL_SIZE>",
                "NODATA": 0,
            },
            outputs={"OUTPUT": "building_height_raw.tif"},
            checks=[
                "训练反思规则：建筑外 NoData 应转为 0，表面分析工具才有连续高度面。",
                "建筑高度是离散值，边界不要用会模糊高度的重采样方式。",
            ],
        ),
        WorkflowStep(
            id="27_nodata_to_zero",
            title="NoData 赋 0",
            purpose="把建筑外 NoData 转为地面 0，同时保留建筑高度。",
            engine="qgis_processing",
            algorithm="gdal:rastercalculator",
            inputs={"INPUT_A": "building_height_raw.tif"},
            parameters={"BAND_A": 1, "FORMULA": "where(isnan(A), 0, A)", "RTYPE": 5},
            outputs={"OUTPUT": "building_height_zero.tif"},
            checks=["核心规则：NoData 不参与邻域分析，坡向或山体阴影前应先转为 0。"],
        ),
        WorkflowStep(
            id="28_building_aspect",
            title="建筑高度面坡向",
            purpose="从建筑高度面计算坡向，用于识别背光面。",
            engine="qgis_processing",
            algorithm="gdal:aspect",
            inputs={"INPUT": "building_height_zero.tif"},
            parameters={"BAND": 1},
            outputs={"OUTPUT": "building_aspect.tif"},
            checks=["坡向值一般为 0 北、90 东、180 南、270 西；平坦像元常为 -1。"],
        ),
        WorkflowStep(
            id="29_backlit_sides",
            title="背光面提取",
            purpose="提取冬至正午条件下的背光面，用于日照判读。",
            engine="qgis_processing",
            algorithm="gdal:rastercalculator",
            inputs={"INPUT_A": "building_aspect.tif"},
            parameters={
                "BAND_A": 1,
                "FORMULA": "logical_or(logical_and(A >= 0, A <= 90), logical_and(A >= 270, A <= 360))",
                "RTYPE": 1,
            },
            outputs={"OUTPUT": "backlit_binary.tif"},
            checks=["冬至正午示例：太阳方位角 180 度，高度角 44.3 度；背光坡向可取 [0,90] ∪ [270,360]。"],
        ),
        WorkflowStep(
            id="30_backlit_height",
            title="背光高度栅格",
            purpose="只给背光像元保留真实建筑高度，供后续阴影建模使用。",
            engine="qgis_processing",
            algorithm="gdal:rastercalculator",
            inputs={"INPUT_A": "backlit_binary.tif", "INPUT_B": "building_height_zero.tif"},
            parameters={"BAND_A": 1, "BAND_B": 1, "FORMULA": "A * B", "RTYPE": 5},
            outputs={"OUTPUT": "backlit_height.tif"},
            checks=[
                "不要直接把 0/1 二值栅格用于山体阴影，否则建筑会变成 0-1 米微地形。",
                "如果题目只要求背光面判读，不要直接使用完整建筑高度面替代。",
            ],
        ),
        WorkflowStep(
            id="31_sun_shadow_hillshade",
            title="QGIS 光照/阴影栅格",
            purpose="使用太阳方位角和高度角生成 QGIS 原生光照栅格。",
            engine="qgis_processing",
            algorithm="native:hillshade",
            inputs={"INPUT": "backlit_height.tif"},
            parameters={"Z_FACTOR": 1, "AZIMUTH": "<SUN_AZIMUTH>", "V_ANGLE": "<SUN_ALTITUDE>"},
            outputs={"OUTPUT": "building_shadow.tif"},
            checks=[
                "QGIS 原生山体阴影支持太阳方位角和高度角。",
                "它不等同于 ArcGIS 的 Sun Shadow Volume；真实 3D 投影阴影应转入 3D 工具或插件。",
            ],
        ),
        WorkflowStep(
            id="32_extract_shadow_to_points",
            title="提取阴影值至点",
            purpose="把阴影栅格值提取到建筑质心或候选点，用于最终日照判读。",
            engine="pending",
            algorithm="QGIS 采样栅格值 / ArcGIS 提取值至点",
            inputs={"POINTS": "<CANDIDATE_POINTS>", "RASTER": "building_shadow.tif"},
            outputs={"OUTPUT": "candidate_sunlight_judgement.gpkg"},
            checks=["常见判读：阴影值为 0 表示阴影，非 0 表示受光；仍需核对具体工具输出约定。"],
        ),
        WorkflowStep(
            id="33_sun_shadow_volume_reference",
            title="3D 太阳阴影体参考",
            purpose="真实 3D 场景日照分析应使用 Sun Shadow Volume，而不是手算太阳角替代。",
            engine="pending",
            algorithm="ArcGIS Sun Shadow Volume / 3D Analyst 同类工具",
            inputs={"BUILDING_3D": "<BUILDING_3D>"},
            parameters={"DATE_TIME": "<SUN_DATETIME>"},
            outputs={"OUTPUT": "sun_shadow_volume.gpkg"},
            checks=["训练反思：3D 场景优先找 Sun Shadow Volume；除非题目明确要求，否则不要手算太阳角替代。"],
        ),
    ]


def _site_selection_steps() -> list[WorkflowStep]:
    return [
        WorkflowStep(
            id="40_buffer",
            title="缓冲区",
            purpose="生成基于距离的约束区或影响范围。",
            engine="qgis_processing",
            algorithm="native:buffer",
            inputs={"INPUT": "<TARGET_LAYER>"},
            parameters={
                "DISTANCE": "<distance>",
                "SEGMENTS": 5,
                "END_CAP_STYLE": 0,
                "JOIN_STYLE": 0,
                "MITER_LIMIT": 2,
                "DISSOLVE": True,
            },
            outputs={"OUTPUT": "buffer_zone.gpkg"},
            checks=["距离分析前必须确认图层使用米制投影坐标系。"],
        ),
        WorkflowStep(
            id="41_erase",
            title="擦除/差集",
            purpose="移除限制区域，或生成剩余适宜区域。",
            engine="qgis_processing",
            algorithm="native:difference",
            inputs={"INPUT": "<TARGET_LAYER>", "OVERLAY": "buffer_zone.gpkg"},
            outputs={"OUTPUT": "eligible_area.gpkg"},
            checks=["差集顺序很重要：保留 INPUT，移除 OVERLAY。"],
        ),
        WorkflowStep(
            id="42_select_by_location",
            title="按位置提取",
            purpose="根据空间关系提取候选要素。",
            engine="qgis_processing",
            algorithm="native:extractbylocation",
            inputs={"INPUT": "<TARGET_LAYER>", "INTERSECT": "eligible_area.gpkg"},
            parameters={"PREDICATE": 0},
            outputs={"OUTPUT": "selected_candidates.gpkg"},
        ),
    ]


def _viewshed_steps() -> list[WorkflowStep]:
    return [
        WorkflowStep(
            id="43_viewshed",
            title="可视域",
            purpose="从候选观察点估算可见区域。",
            engine="qgis_processing",
            algorithm="gdal:viewshed",
            inputs={"INPUT": "<DEM>"},
            parameters={
                "BAND": 1,
                "OBSERVER": "<OBSERVER_XY>",
                "OBSERVER_HEIGHT": "<observer_height>",
                "TARGET_HEIGHT": 0,
                "MAX_DISTANCE": "<MAX_DISTANCE>",
            },
            outputs={"OUTPUT": "viewshed.tif"},
            checks=[
                "QGIS GDAL 可视域通常一次使用一个观察点坐标，例如 x,y。",
                "多个候选点需要批处理循环，或先选择一个候选点运行。",
                "确认观察高度、目标高度、分析半径和 DEM 垂直单位。",
            ],
        ),
    ]


def _reclass_change_steps() -> list[WorkflowStep]:
    return [
        WorkflowStep(
            id="50_reclass",
            title="重分类",
            purpose="统一类别编码，或仅保留目标类别。",
            engine="qgis_processing",
            algorithm="native:reclassifybytable",
            outputs={"OUTPUT": "reclassified.tif"},
            checks=["提取目标类别时，其他类别可按题目要求赋为 NoData。"],
        ),
        WorkflowStep(
            id="51_change_code",
            title="变化编码",
            purpose="按 early_class * 10 + late_class 生成土地利用转移编码。",
            engine="pending",
            algorithm="栅格计算器",
            parameters={"expression": "early * 10 + late"},
            outputs={"change_code": "change_code.tif"},
            checks=["图例必须解释每个编码对应的前期类别和后期类别。"],
        ),
        WorkflowStep(
            id="52_transition_table",
            title="转移矩阵",
            purpose="统计土地利用转移的数量或面积。",
            engine="autogis",
            algorithm="transition_matrix",
            outputs={"table": "transition_matrix.csv"},
        ),
    ]


def _analysis_text(analysis: dict[str, Any] | None) -> str:
    return json.dumps(analysis or {}, ensure_ascii=False)


def _formula_indicator_steps(task: str, analysis: dict[str, Any] | None = None) -> list[WorkflowStep]:
    combined = f"{task}\n{_analysis_text(analysis)}"
    steps: list[tuple[int, WorkflowStep]] = []
    if _contains_any(combined, ["空地率"]):
        steps.append(
            (
                _first_keyword_index(combined, ["空地率"]),
                WorkflowStep(
                id="80_open_space_ratio",
                title="空地率计算",
                purpose="按公式计算未被建筑覆盖面积占片区总面积的比例。",
                engine="pending",
                algorithm="叠置分析 + 几何面积计算 + 字段计算器",
                inputs={"ZONE_LAYER": "<片区面>", "BUILDINGS": "<建筑物面>"},
                outputs={"OUTPUT": "open_space_ratio.gpkg"},
                checks=[
                    "公式一般为 (片区面积 - 建筑覆盖面积) / 片区面积。",
                    "建筑覆盖面积应按片区汇总，叠置后必须重新计算面积字段。",
                ],
                ),
            )
        )
    if _contains_any(combined, ["TCI", "地形复杂度", "Ln(R", "ln(r"]):
        steps.append(
            (
                _first_keyword_index(combined, ["TCI", "地形复杂度", "Ln(R", "ln(r"]),
                WorkflowStep(
                id="81_tci_raster",
                title="TCI 地形复杂度指数",
                purpose="根据 R 和 S 生成像元级 TCI 栅格，再按乡镇统计均值。",
                engine="pending",
                algorithm="焦点统计 + 坡度 + 栅格计算器 + 分区统计",
                inputs={"DEM": "<DEM>", "ZONE_LAYER": "<乡镇边界>"},
                parameters={"FORMULA": "ln(R + 0.01) + ln(S + 0.01)"},
                outputs={"TCI": "tci.tif", "TABLE": "town_tci.csv"},
                checks=[
                    "必须确认 R 的定义是高程极差、标准差还是其他邻域指标。",
                    "Ln 是自然对数；R 和 S 的单位、NoData 处理要一致。",
                    "乡镇 TCI 是像元 TCI 的均值，不是直接对 DEM 求均值。",
                ],
                ),
            )
        )
    if _contains_any(combined, ["LSI", "耕地规模化"]):
        steps.append(
            (
                _first_keyword_index(combined, ["LSI", "耕地规模化"]),
                WorkflowStep(
                id="82_lsi_index",
                title="LSI 耕地规模化指数",
                purpose="按乡镇统计耕地面积 A 和满足阈值的耕地斑块数量 N，再代入公式。",
                engine="pending",
                algorithm="按属性筛选 + 多部件转单部件 + 汇总统计 + 字段计算器",
                inputs={"FARMLAND": "<耕地图斑>", "ZONE_LAYER": "<乡镇边界>"},
                outputs={"OUTPUT": "lsi_index.gpkg"},
                checks=[
                    "先确认耕地编码和面积阈值，例如面积 >= 1000 平方米。",
                    "A 和 N 必须按同一乡镇分组统计，面积单位按题目要求换算。",
                ],
                ),
            )
        )
    if _contains_any(combined, ["夜间灯光", "GDP", "权重"]):
        steps.append(
            (
                _first_keyword_index(combined, ["夜间灯光", "GDP", "权重"]),
                WorkflowStep(
                id="83_light_weighted_gdp",
                title="夜间灯光加权 GDP 分配",
                purpose="按夜间灯光权重把区县 GDP 分配到乡镇。",
                engine="pending",
                algorithm="分区统计 + 属性连接 + 字段计算器",
                inputs={"LIGHT_RASTER": "<夜间灯光栅格>", "ZONE_LAYER": "<乡镇边界>", "GDP_TABLE": "<GDP表>"},
                outputs={"OUTPUT": "town_gdp_weighted.gpkg"},
                checks=[
                    "每个区县内乡镇灯光权重之和应约等于 1。",
                    "必须区分灯光 0 值和 NoData；区县代码、乡镇代码要能连接。",
                ],
                ),
            )
        )
    return [step for _, step in sorted(steps, key=lambda item: item[0])]


def _zonal_stats_steps() -> list[WorkflowStep]:
    return [
        WorkflowStep(
            id="60_zonal_statistics",
            title="分区统计",
            purpose="按分区面统计栅格值。",
            engine="qgis_processing",
            algorithm="native:zonalstatisticsfb",
            inputs={"INPUT": "<ZONE_LAYER>", "INPUT_RASTER": "<VALUE_RASTER>"},
            parameters={"COLUMN_PREFIX": "stat_", "STATISTICS": "<STATS>"},
            outputs={"OUTPUT": "zonal_statistics.gpkg"},
            checks=["确认分区矢量和栅格的坐标系、范围兼容。"],
        )
    ]


def _attribute_table_steps() -> list[WorkflowStep]:
    return [
        WorkflowStep(
            id="65_join_attributes",
            title="按字段连接属性",
            purpose="使用匹配字段把表格属性连接到目标矢量图层。",
            engine="qgis_processing",
            algorithm="native:joinattributestable",
            inputs={"INPUT": "<TARGET_LAYER>", "INPUT_2": "<JOIN_TABLE>"},
            parameters={
                "FIELD": "<TARGET_FIELD>",
                "FIELD_2": "<JOIN_FIELD>",
                "FIELDS_TO_COPY": "<FIELDS_TO_COPY>",
                "METHOD": 1,
                "DISCARD_NONMATCHING": False,
            },
            outputs={"OUTPUT": "joined_attributes.gpkg"},
            checks=[
                "确认两个连接字段的编码格式和文本/数字类型一致。",
                "连接后打开属性表，检查未匹配记录。",
            ],
        )
    ]


def _vector_edit_steps(task: str) -> list[WorkflowStep]:
    steps: list[WorkflowStep] = []

    if _contains_any(task, ["create feature", "digitize", "new feature", "新增要素", "创建要素", "点要素", "线要素", "面要素", "绘制", "数字化", "新建", "新建点", "新建线", "新建面"]):
        steps.append(
            WorkflowStep(
                id="70_create_features",
                title="创建/数字化要素",
                purpose="在后续处理前创建新的点、线或面要素。",
                engine="pending",
                algorithm="QGIS 编辑会话或 PyQGIS 创建要素",
                inputs={"TEMPLATE_LAYER": "<TEMPLATE_LAYER>"},
                parameters={"GEOMETRY_TYPE": "<GEOMETRY_TYPE>"},
                outputs={"OUTPUT": "created_features.gpkg"},
                checks=[
                    "创建要素通常需要人工确认几何，除非题目给出明确坐标或构造规则。",
                    "编辑前确认目标坐标系、捕捉、拓扑规则和必填属性字段。",
                ],
            )
        )

    if _contains_any(task, ["move", "translate", "平移", "移动", "偏移"]):
        steps.append(
            WorkflowStep(
                id="71_translate_geometry",
                title="移动/平移要素",
                purpose="按确认的 X/Y 偏移量移动要素。",
                engine="qgis_processing",
                algorithm="native:translategeometry",
                inputs={"INPUT": "<TARGET_LAYER>"},
                parameters={"DELTA_X": "<DELTA_X>", "DELTA_Y": "<DELTA_Y>"},
                outputs={"OUTPUT": "translated_features.gpkg"},
                checks=["偏移量使用当前图层坐标单位；米制偏移前确认投影坐标系。"],
            )
        )

    if _contains_any(task, ["rotate", "旋转", "转动", "角度"]):
        steps.append(
            WorkflowStep(
                id="72_rotate_features",
                title="旋转要素",
                purpose="按确认的角度和锚点旋转要素。",
                engine="qgis_processing",
                algorithm="native:rotatefeatures",
                inputs={"INPUT": "<TARGET_LAYER>"},
                parameters={"ANGLE": "<ANGLE>", "ANCHOR": "<ANCHOR>"},
                outputs={"OUTPUT": "rotated_features.gpkg"},
                checks=["确认角度方向、单位和旋转锚点；正式执行前先预览。"],
            )
        )

    if _contains_any(task, ["split", "cut", "divide", "切割", "分割", "划分", "切分"]):
        steps.append(
            WorkflowStep(
                id="73_split_with_lines",
                title="按线分割要素",
                purpose="使用分割线图层切分面或线要素。",
                engine="qgis_processing",
                algorithm="native:splitwithlines",
                inputs={"INPUT": "<TARGET_LAYER>", "LINES": "<SPLIT_LAYER>"},
                outputs={"OUTPUT": "split_features.gpkg"},
                checks=["确认分割线穿过目标要素，且坐标系兼容。"],
            )
        )

    if _contains_any(task, ["clip", "裁剪", "按范围", "研究区", "掩膜"]):
        steps.append(
            WorkflowStep(
                id="74_clip_vector",
                title="裁剪矢量图层",
                purpose="保留边界或掩膜范围内的目标要素。",
                engine="qgis_processing",
                algorithm="native:clip",
                inputs={"INPUT": "<TARGET_LAYER>", "OVERLAY": "<OVERLAY_LAYER>"},
                outputs={"OUTPUT": "clipped_features.gpkg"},
                checks=["确认题目要求的是裁剪、相交还是擦除，这三者输出不同。"],
            )
        )

    if _contains_any(task, ["subdivide", "partition", "网格", "鱼网", "分块", "划分"]):
        steps.append(
            WorkflowStep(
                id="75_subdivide",
                title="细分要素",
                purpose="把复杂面拆成更小部分，便于后续处理。",
                engine="qgis_processing",
                algorithm="native:subdivide",
                inputs={"INPUT": "<TARGET_LAYER>"},
                parameters={"MAX_NODES": "<MAX_NODES>"},
                outputs={"OUTPUT": "subdivided_features.gpkg"},
                checks=["技术性拆分用细分；若题目有明确分割线，应使用按线分割。"],
            )
        )

    return steps


def plan_task(task: str, data_paths: list[Path] | None = None, analysis: dict[str, Any] | None = None) -> Workflow:
    data_paths = data_paths or []
    steps = [_data_check_step()]
    task_types: list[tuple[int, str]] = []
    missing_inputs: list[str] = []
    assumptions = ["当前为辅助流程草案。执行前必须确认数据和关键参数。"]

    if not task.strip():
        return Workflow(
            task=task,
            task_types=["unknown"],
            assumptions=assumptions,
            missing_inputs=["未提供题目文本。请先扫描文件夹或粘贴题目。"],
            data_paths=data_paths,
            steps=steps,
        )

    step_groups: list[tuple[int, list[WorkflowStep]]] = []

    hydro_words = ["hydrology", "fill", "flow", "accumulation", "stream", "watershed", "水文", "填洼", "流向", "流量", "河网", "流域", "汇流"]
    if _contains_any(task, hydro_words):
        order = _first_keyword_index(task, hydro_words)
        task_types.append((order, "hydrology"))
        step_groups.append((order, _hydrology_steps()))
        if not _contains_any(task, ["threshold", "catchment area", "阈值", "集水面积", ">500"]):
            missing_inputs.append("河网提取阈值或目标集水面积")

    is_sunlight_task = _is_building_sunlight_task(task)

    terrain_words = ["slope", "aspect", "hillshade", "illumination", "dem", "坡度", "坡向", "光照", "山体阴影", "高程", "地形"]
    if _contains_any(task, terrain_words) and not is_sunlight_task:
        order = _first_keyword_index(task, terrain_words)
        task_types.append((order, "terrain"))
        step_groups.append((order, _terrain_steps()))

    if is_sunlight_task:
        sunlight_words = ["sunlight", "sun shadow", "solar", "solar radiation", "building sunlight", "日照", "建筑日照", "太阳阴影", "背光面", "冬至"]
        order = _first_keyword_index(task, sunlight_words)
        task_types.append((order, "building_sunlight"))
        step_groups.append((order, _sunlight_analysis_steps()))

    site_words = ["site", "suitability", "buffer", "erase", "intersect", "select by location", "service area", "选址", "适宜", "缓冲", "擦除", "相交", "按位置", "候选区", "噪声", "最小距离", "距离筛选"]
    if _is_site_selection_context(task):
        order = _first_keyword_index(task, site_words)
        task_types.append((order, "site_selection"))
        step_groups.append((order, _site_selection_steps()))

    viewshed_words = ["viewshed", "visibility", "visible area", "可视域", "视域", "可视", "观察点", "瞭望塔"]
    if _contains_any(task, viewshed_words):
        order = _first_keyword_index(task, viewshed_words)
        task_types.append((order, "viewshed"))
        step_groups.append((order, _viewshed_steps()))

    reclass_words = ["reclass", "change", "transition", "land use", "重分类", "变化", "转移", "转移矩阵", "土地利用", "耕地"]
    if _contains_any(task, reclass_words):
        order = _first_keyword_index(task, reclass_words)
        task_types.append((order, "reclass_change"))
        step_groups.append((order, _reclass_change_steps()))

    zonal_words = ["zonal", "zone statistics", "分区统计", "区域统计", "乡镇", "统计", "均值", "总和"]
    if _contains_any(task, zonal_words):
        order = _first_keyword_index(task, zonal_words)
        task_types.append((order, "zonal_statistics"))
        step_groups.append((order, _zonal_stats_steps()))

    formula_steps = _formula_indicator_steps(task, analysis=analysis)
    if formula_steps:
        formula_words = ["空地率", "TCI", "地形复杂度", "LSI", "耕地规模化", "夜间灯光", "GDP", "权重", "汇流累积量阈值"]
        order = _first_keyword_index(task, formula_words)
        task_types.append((order, "formula_indicators"))
        step_groups.append((order, formula_steps))

    join_words = ["join", "table", "csv", "xlsx", "dbf", "attribute", "field", "连接", "属性表", "字段", "表格", "挂接", "追加"]
    if _contains_any(task, join_words):
        order = _first_keyword_index(task, join_words)
        task_types.append((order, "attribute_join"))
        step_groups.append((order, _attribute_table_steps()))

    edit_words = ["create feature", "digitize", "move", "translate", "rotate", "split", "cut", "divide", "clip", "subdivide", "新增要素", "创建要素", "点要素", "线要素", "面要素", "绘制", "数字化", "新建", "移动", "平移", "旋转", "切割", "分割", "划分", "裁剪", "分块", "鱼网"]
    if _contains_any(task, edit_words):
        order = _first_keyword_index(task, edit_words)
        task_types.append((order, "vector_edit_geometry"))
        step_groups.append((order, _vector_edit_steps(task)))

    if not task_types:
        task_types.append((999999, "unknown"))
        missing_inputs.append("暂时无法分类题目。请补充更明确的操作关键词，或手动选择数据角色。")

    if not data_paths:
        missing_inputs.append("未提供真实输入数据路径。")

    for _, group_steps in sorted(step_groups, key=lambda item: item[0]):
        steps.extend(group_steps)

    return Workflow(
        task=task,
        task_types=[name for _, name in sorted(task_types, key=lambda item: item[0])],
        assumptions=assumptions,
        missing_inputs=missing_inputs,
        data_paths=data_paths,
        steps=steps,
    )
