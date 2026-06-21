from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any


TABLE_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def _safe_name(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", path.stem)[:80] or "table"


def _read_table(path: Path):
    import pandas as pd

    suffix = path.suffix.lower()
    if suffix == ".csv":
        for encoding in ("utf-8-sig", "gbk", "utf-8"):
            try:
                return pd.read_csv(path, encoding=encoding)
            except UnicodeDecodeError:
                continue
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"暂不支持该表格格式：{suffix}")


def _task_formula_hints(task: str, columns: list[str]) -> list[str]:
    lowered = task.lower()
    joined_columns = " ".join(columns).lower()
    hints: list[str] = []
    if "gdp" in lowered or "gdp" in joined_columns or "夜间灯光" in task:
        hints.append("若进行 GDP 分配，需检查区县代码、乡镇代码、GDP 字段和夜间灯光权重字段是否可连接。")
    if "空地率" in task:
        hints.append("空地率通常需要片区面积、建筑覆盖面积，并确认面积单位。")
    if "lsi" in lowered or "耕地规模化" in task:
        hints.append("LSI 需要按乡镇统计耕地总面积 A 和满足面积阈值的斑块数量 N。")
    if "tci" in lowered or "地形复杂度" in task:
        hints.append("TCI 的表格结果应来自栅格分区统计均值，不能直接用 DEM 均值代替。")
    if not hints:
        hints.append("未识别到特定公式关键词；优先检查连接字段、空值、重复值和数值异常。")
    return hints


def _numeric_summary(df) -> list[dict[str, Any]]:
    import numpy as np

    numeric = df.select_dtypes(include=[np.number])
    rows: list[dict[str, Any]] = []
    for col in numeric.columns[:30]:
        series = numeric[col].dropna()
        if series.empty:
            continue
        rows.append(
            {
                "column": str(col),
                "count": int(series.count()),
                "min": _number(series.min()),
                "max": _number(series.max()),
                "mean": _number(series.mean()),
                "std": _number(series.std()) if series.count() > 1 else None,
                "zero_count": int((series == 0).sum()),
                "negative_count": int((series < 0).sum()),
            }
        )
    return rows


def _number(value: Any) -> float | int | None:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else round(number, 6)


def _make_chart(df, output_dir: Path, table_path: Path) -> str | None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    numeric = df.select_dtypes(include=[np.number])
    if numeric.empty:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    column = numeric.columns[0]
    series = numeric[column].dropna()
    if series.empty:
        return None
    chart_path = output_dir / f"{_safe_name(table_path)}_{column}_hist.png"
    plt.figure(figsize=(7, 4))
    plt.hist(series, bins=min(30, max(6, int(math.sqrt(len(series))))), color="#1d6f8f", edgecolor="white")
    plt.title(f"{column} 分布")
    plt.xlabel(str(column))
    plt.ylabel("频数")
    plt.tight_layout()
    plt.savefig(chart_path, dpi=150)
    plt.close()
    return str(chart_path)


def profile_table(path: Path, task: str = "", output_dir: Path | None = None) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "path": str(path), "error": "表格路径不存在。"}
    if path.suffix.lower() not in TABLE_EXTENSIONS:
        return {"ok": False, "path": str(path), "error": f"暂不支持该格式：{path.suffix}"}
    try:
        df = _read_table(path)
    except Exception as exc:
        return {"ok": False, "path": str(path), "error": str(exc)}

    columns = [str(col) for col in df.columns]
    nulls = df.isna().sum()
    duplicate_rows = int(df.duplicated().sum())
    duplicate_columns = [str(col) for col in df.columns if df[col].duplicated().sum() > 0][:20]
    chart_path = _make_chart(df, output_dir or path.parent, path)
    numeric = _numeric_summary(df)
    warnings: list[str] = []
    if duplicate_rows:
        warnings.append(f"发现 {duplicate_rows} 行完全重复记录，连接或统计前需要确认是否应去重。")
    high_null = [str(col) for col in df.columns if len(df) and nulls[col] / len(df) > 0.2]
    if high_null:
        warnings.append("这些字段空值比例超过 20%：" + "、".join(high_null[:10]))
    if not numeric:
        warnings.append("未识别到数值字段；如果题目需要公式计算，请检查字段类型是否被读成文本。")

    return {
        "ok": True,
        "path": str(path),
        "name": path.name,
        "rows": int(len(df)),
        "columns": columns,
        "dtypes": {str(col): str(dtype) for col, dtype in df.dtypes.items()},
        "null_counts": {str(col): int(count) for col, count in nulls.items() if int(count) > 0},
        "duplicate_rows": duplicate_rows,
        "duplicate_columns": duplicate_columns,
        "numeric_summary": numeric,
        "formula_hints": _task_formula_hints(task, columns),
        "warnings": warnings,
        "chart_path": chart_path,
    }


def profile_tables(paths: list[Path], task: str = "", output_dir: Path | None = None) -> dict[str, Any]:
    results = [profile_table(path, task=task, output_dir=output_dir) for path in paths]
    return {"ok": True, "results": results}
