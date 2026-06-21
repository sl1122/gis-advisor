# GIS 模块库与界面端优化方案

更新时间：2026-06-20

## 目标定位

AutoGIS 不应做成低配 QGIS。它的价值是把“题目理解、数据角色识别、操作模块推荐、参数确认、执行记录、结果检查、复盘记忆”串起来。

真正计算仍交给成熟工具：

- QGIS Processing：通用矢量、栅格、模型化流程。
- GDAL/OGR：格式转换、栅格/矢量底层处理。
- GRASS/SAGA：传统 GIS 和地形水文分析。
- WhiteboxTools：地形、水文、栅格和地貌分析。
- Orfeo Toolbox：遥感指数、分类、分割和大影像处理。
- QGIS 插件 Processing Provider：如 QNEAT3 的网络分析能力。

## 网络与开源架构参考

1. QGIS Model Designer  
   参考：https://docs.qgis.org/latest/en/docs/user_manual/processing/modeler.html  
   启发：复杂题目应拆成模型链，多个算法串联并保存参数，而不是每次手工点工具。

2. QGIS Processing Training Manual  
   参考：https://docs.qgis.org/latest/en/docs/training_manual/processing/index.html  
   启发：网页端应该围绕 Processing 算法、参数、日志、输出文件组织，而不是围绕“按钮堆叠”组织。

3. QNEAT3  
   参考：https://github.com/root676/QNEAT3  
   启发：网络分析适合通过 QGIS Processing Provider 接入，包括最近设施、OD 矩阵、服务区和可达性。

4. Orfeo Toolbox  
   参考：https://www.orfeo-toolbox.org/CookBook/  
   启发：遥感处理不应只靠 QGIS 原生工具，大影像、分类、分割、变化检测应优先考虑 OTB/GDAL 这类后端。

5. WhiteboxTools  
   参考：https://www.whiteboxgeo.com/manual/wbt_book/available_tools/hydrological_analysis.html  
   启发：地形和水文只是其中一部分，Whitebox 也可作为通用地形/栅格分析后端。

## 模块库结构

模块库文件：`autogis/module_library.json`

每个模块包含：

- `id`：稳定模块编号。
- `title`：界面显示名称。
- `category`：题目理解、数据预处理、矢量分析、遥感处理等类别。
- `keywords`：用于题目匹配。
- `input_roles`：必须数据角色，如 DEM、boundary、vector、table。
- `optional_roles`：可选数据角色。
- `backend`：推荐执行后端，如 QGIS Processing、GDAL、WhiteboxTools、OTB、QNEAT3。
- `status_policy`：可直接执行、需映射、需确认、需插件等。
- `steps`：操作链。
- `outputs`：推荐输出。
- `checks`：训练反思中的易错点。
- `blockers`：当前需要用户确认或插件接入的条件。

## 已整理模块

1. 题目拆解与题组管理  
   用于把多题目拆成题组、空格答案、图件要求和数据组。

2. 数据标准化与预处理  
   投影、格式转换、ArcInfo Grid 转 GeoTIFF、裁剪、掩膜、NoData 检查。

3. 矢量叠置、缓冲与面积统计  
   缓冲、相交、擦除、融合、重算面积、统计表输出。

4. 字段计算与属性表处理  
   字段类型、Join、Null 检查、文本拼接、条件赋值。

5. 栅格计算、重分类与 NoData 修复  
   Con/SetNull、分类编码、NoData 传播、类别面积统计。

6. 遥感指数、分类与变化检测  
   NDVI/指数、监督分类、变化检测、精度评价。

7. 地形分析  
   坡度、坡向、山体阴影、地形复杂度。

8. 水文分析  
   填洼、流向、流量、河网、流域、TWI。

9. 可视域与观察点分析  
   观察点高度、人工 DEM、可视域面积统计。

10. 分区统计与指标回连  
    Zonal Statistics、结果回连、Null 检查、指标制图。

11. 选址适宜性与多准则评价  
    约束排除、因子标准化、权重叠加、候选点排序。

12. 网络分析  
    QNEAT3/网络分析：最近设施、服务区、OD 矩阵、可达性。

13. 制图输出与符号系统检查  
    连续/离散符号系统、图例、比例尺、指北针、导出。

## 与训练反思的对应关系

训练反思不应只是文档，而应进入执行前检查：

- 坐标系：距离/面积前必须投影。
- 处理范围：栅格分析前确认 Extent 和 Mask。
- 字段：Join 后检查 Null，字段类型不对不能拼接。
- 面积：裁剪、相交、融合后必须重算。
- 栅格：离散栅格重采样用最近邻，NoData 会传播。
- 水文：填洼是水文前置，阈值按像元面积换算。
- 可视域：OFFSETA 不是绝对高程，不可见像元应设为 NoData。
- 制图：连续栅格用拉伸，分类栅格用分类图例。

## 界面端优化方向

当前已接入：扫描后自动显示模块库推荐。

下一步建议：

1. 题组视图  
   把试题按“第 1 题 / 第 2 题 / 第 3 题”拆分，并绑定对应数据组。

2. 模块详情页  
   点击模块后显示参数、输入图层、执行后端、易错点、结果文件。

3. 执行按钮分级  
   - 可直接执行：格式转换、坡度、坡向、山体阴影、基础统计。
   - 需确认参数：缓冲距离、河网阈值、重分类编码、权重。
   - 需人工判断：补绘、复杂制图、字段语义识别。

4. 结果浏览  
   支持查看栅格缩略图、矢量属性表、输出日志、字段摘要。

5. 复盘记忆  
   记录每次题目、模块、参数、错误和最终结果，形成个人训练记忆库。

## 结论

这个项目的方向不是“替代 QGIS”，而是“用你的解题习惯组织 QGIS 和开源 GIS 工具”。模块库是核心资产，网页只是它的操作界面。
