# GIS Advisor

GIS Advisor 是一个面向 GIS 作业、竞赛训练和科研前处理的题目分析与操作指导工具。项目定位不是替代 ArcGIS Pro 或 QGIS 自动完成所有数据处理，而是优先完成题目拆解、数据角色识别、公式理解、操作路线生成、风险提示和结果检查。

## 核心功能

- 扫描项目文件夹，识别题目文档、DEM、栅格、矢量、表格和普通文档。
- 读取 PDF / DOCX / TXT / Markdown 题面，提取正文和疑似公式。
- 使用本地规则或 AI API 分析题目，生成 ArcGIS Pro 优先、QGIS 免费替代的操作路线。
- 根据训练反思知识库匹配相似题、易错点和操作经验。
- 生成辅助流程树，区分可自动执行步骤和需要人工确认的步骤。
- 使用 pandas / numpy / matplotlib 对表格做统计核查、字段检查和图表输出。
- 可调用 QGIS / GDAL / WhiteboxTools 执行部分确定性步骤。

## 快速开始

```powershell
cd D:\文档\ドキュメント\autogis
python -m pip install -e .
python -m autogis doctor
python -B -X utf8 -m autogis web --host 127.0.0.1 --port 8765 --no-open
```

打开：

```text
http://127.0.0.1:8765/
```

## AI 配置

DeepSeek：

```powershell
$env:DEEPSEEK_API_KEY="你的 Key"
$env:DEEPSEEK_MODEL="deepseek-v4-pro"
```

也可以在网页中切换模型名称。API Key 不应写入源码或 Git。

## 仓库结构

```text
gis-advisor/
├── autogis/                 # 应用源码和 Web 界面
├── docs/                    # 知识库、训练反思模板、系统设计文档
├── data/                    # 本地数据库说明，真实 db 默认不提交
├── outputs/                 # 生成的解题指导和图表，默认不提交
├── scripts/                 # 辅助脚本
├── pyproject.toml           # Python 依赖
├── README.md
├── LICENSE
└── .gitignore
```

## 使用建议

1. 先扫描真实项目文件夹。
2. 检查题目文本是否提取完整，尤其是 PDF 公式。
3. 点击“分析题目”，查看 AI 分析、公式解释、训练反思匹配和风险提示。
4. 点击“生成辅助流程”，查看可执行步骤和需人工确认步骤。
5. 对表格类题目点击“统计核查”，检查字段、空值、重复值和数值分布。
6. 只有参数明确、风险低的步骤才建议自动执行。

## 许可

MIT License.
