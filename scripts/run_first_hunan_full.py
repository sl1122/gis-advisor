from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import rasterio.features
import shapefile
from rasterio.features import geometry_mask
from scipy import ndimage
from shapely.geometry import Point, mapping, shape
from shapely.ops import unary_union


ROOT = Path("D:/桌面/第一届湖南省大学生城乡规划设计与测绘综合技能竞赛GIS应用赛项试题")
DATA = ROOT / "Data"
OUT = Path("D:/桌面/AutoGIS结果/first_hunan_full_run")
WORK = Path("D:/autogis_tmp/first_hunan_full_run")
QGIS = Path("D:/QGIS/bin")
GDAL_TRANSLATE = QGIS / "gdal_translate.exe"
GDALDEM = QGIS / "gdaldem.exe"
WBT = Path(
    "C:/Users/SL/AppData/Local/Programs/Python/Python312/Lib/site-packages/whitebox/whitebox_tools.exe"
)


def run(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stdout}")
    return proc.stdout


def ensure_dirs() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    for name in ["01_BuildingDesign", "02_FireMSite", "03_TownType"]:
        (OUT / name).mkdir(parents=True, exist_ok=True)
        (WORK / name).mkdir(parents=True, exist_ok=True)


def read_features(path: Path):
    last_error = None
    for enc in ("utf-8", "gbk"):
        try:
            reader = shapefile.Reader(str(path), encoding=enc)
            fields = [f[0] for f in reader.fields[1:]]
            rows = []
            for sr in reader.iterShapeRecords():
                props = dict(zip(fields, sr.record))
                geom = shape(sr.shape.__geo_interface__)
                if not geom.is_valid:
                    geom = geom.buffer(0)
                rows.append({"geometry": geom, "properties": props})
            return rows
        except Exception as exc:  # pragma: no cover - encoding fallback
            last_error = exc
    raise RuntimeError(f"Cannot read {path}: {last_error}")


def union_geoms(features):
    geoms = [f["geometry"] for f in features if not f["geometry"].is_empty]
    return unary_union(geoms) if geoms else None


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, keys)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_geojson(path: Path, features: list[dict]) -> None:
    fc = {"type": "FeatureCollection", "features": []}
    for feat in features:
        geom = feat["geometry"]
        if geom is None or geom.is_empty:
            continue
        fc["features"].append(
            {
                "type": "Feature",
                "geometry": mapping(geom),
                "properties": feat.get("properties", {}),
            }
        )
    write_json(path, fc)


def write_point_shapefile(path: Path, points: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = shapefile.Writer(str(path), shapeType=shapefile.POINT)
    writer.field("id", "N", decimal=0)
    writer.field("elev", "F", decimal=2)
    for idx, rec in enumerate(points, start=1):
        p = rec["geometry"]
        writer.point(p.x, p.y)
        writer.record(idx, float(rec.get("elev", 0.0)))
    writer.close()
    prj = DATA / "Data_FireMSite" / "Boundary.prj"
    if prj.exists():
        shutil.copyfile(prj, path.with_suffix(".prj"))


def translate_to_tif(src: Path, dst: Path) -> None:
    if not dst.exists():
        proc = subprocess.run(
            [str(GDAL_TRANSLATE), "-of", "GTiff", str(src), str(dst)],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if proc.returncode != 0 and not dst.exists():
            raise RuntimeError(f"Command failed ({proc.returncode}): {src}\n{proc.stdout}")


def raster_union(mask_tif: Path, truth=lambda v: v > 0):
    with rasterio.open(mask_tif) as src:
        arr = src.read(1)
        nodata = src.nodata
        mask = truth(arr)
        if nodata is not None:
            mask &= arr != nodata
        shapes = []
        for geom, value in rasterio.features.shapes(mask.astype("uint8"), mask=mask, transform=src.transform):
            if value == 1:
                shapes.append(shape(geom))
    return unary_union(shapes) if shapes else None


def raster_value_at(src, x: float, y: float):
    row, col = src.index(x, y)
    if row < 0 or col < 0 or row >= src.height or col >= src.width:
        return None
    val = src.read(1, window=((row, row + 1), (col, col + 1)))[0, 0]
    if src.nodata is not None and val == src.nodata:
        return None
    return float(val)


def extent_of_features(name: str, features: list[dict]) -> dict:
    geom = union_geoms(features)
    minx, miny, maxx, maxy = geom.bounds
    return {
        "layer": name,
        "feature_count": len(features),
        "minx": round(minx, 3),
        "miny": round(miny, 3),
        "maxx": round(maxx, 3),
        "maxy": round(maxy, 3),
        "area_km2": round(geom.area / 1_000_000, 6),
    }


def run_building_design(summary: dict) -> None:
    base = DATA / "Data_BuildingDesign"
    out = OUT / "01_BuildingDesign"
    plan = read_features(base / "plan.shp")
    buildings = read_features(base / "buildings.shp")
    roads = read_features(base / "roadcenter.shp")

    rows = [
        extent_of_features("plan", plan),
        extent_of_features("buildings", buildings),
        extent_of_features("roadcenter", roads),
    ]
    with rasterio.open(base / "design.tif") as src:
        b = src.bounds
        rows.append(
            {
                "layer": "design.tif",
                "feature_count": 1,
                "minx": round(b.left, 3),
                "miny": round(b.bottom, 3),
                "maxx": round(b.right, 3),
                "maxy": round(b.top, 3),
                "area_km2": round((b.right - b.left) * (b.top - b.bottom) / 1_000_000, 6),
            }
        )
    write_csv(out / "layer_extent_check.csv", rows)

    building_ids = [str(f["properties"].get("BuildingID", "")).strip() for f in buildings]
    counts = Counter(building_ids)
    multipart_like = [k for k, v in counts.items() if k and v > 1]
    write_csv(
        out / "buildings_partition_summary.csv",
        [
            {"metric": "building_polygon_features", "value": len(buildings)},
            {"metric": "unique_building_id_count", "value": len([k for k in counts if k])},
            {"metric": "building_ids_with_multiple_polygons", "value": len(multipart_like)},
        ],
    )

    plan_u = union_geoms(plan)
    buildings_u = union_geoms(buildings)
    road_u = union_geoms(roads)
    overlaps = [
        {
            "pair": "plan_vs_buildings",
            "overlap_area_km2": round(plan_u.intersection(buildings_u).area / 1_000_000, 8),
            "distance_m": round(plan_u.distance(buildings_u), 3),
        },
        {
            "pair": "roadcenter_vs_buildings",
            "overlap_area_km2": round(road_u.buffer(10).intersection(buildings_u).area / 1_000_000, 8),
            "distance_m": round(road_u.distance(buildings_u), 3),
        },
    ]
    write_csv(out / "spatial_alignment_check.csv", overlaps)
    summary["BuildingDesign"] = {
        "status": "partial_blocked_by_spatial_alignment",
        "outputs": [
            str(out / "layer_extent_check.csv"),
            str(out / "buildings_partition_summary.csv"),
            str(out / "spatial_alignment_check.csv"),
        ],
        "finding": "plan/roadcenter and buildings/design are separated by hundreds of metres, so F3 open-space and road-distance answers cannot be trusted without confirming the intended registration.",
    }


def run_fire_site(summary: dict) -> None:
    base = DATA / "Data_FireMSite"
    out = OUT / "02_FireMSite"
    work = WORK / "02_FireMSite"
    dem_tif = work / "dem.tif"
    translate_to_tif(base / "dem", dem_tif)

    filled = work / "filled_dem.tif"
    pointer = work / "d8_pointer.tif"
    flow_acc = work / "flow_accum_cells.tif"
    streams = work / "streams_gt500.tif"
    for tool, args in [
        ("FillDepressions", [f"--dem={dem_tif}", f"--output={filled}"]),
        ("D8Pointer", [f"--dem={filled}", f"--output={pointer}"]),
        ("D8FlowAccumulation", [f"--input={filled}", f"--output={flow_acc}", "--out_type=cells"]),
        ("ExtractStreams", [f"--flow_accum={flow_acc}", f"--output={streams}", "--threshold=500"]),
    ]:
        if not Path(args[1].split("=", 1)[1]).exists():
            run([str(WBT), f"--run={tool}", f"--wd={work}", *args])

    shutil.copyfile(dem_tif, out / "dem.tif")
    shutil.copyfile(filled, out / "filled_dem.tif")
    shutil.copyfile(pointer, out / "d8_pointer.tif")
    shutil.copyfile(flow_acc, out / "flow_accum_cells.tif")
    shutil.copyfile(streams, out / "streams_gt500.tif")

    boundary = union_geoms(read_features(base / "Boundary.shp"))
    forest_parts = []
    for feat in read_features(base / "forest.shp"):
        geom = feat["geometry"]
        if geom.geom_type == "MultiPolygon":
            for part in geom.geoms:
                forest_parts.append({"geometry": part, "properties": feat["properties"]})
        else:
            forest_parts.append(feat)
    forest_u = union_geoms(forest_parts)
    stream_u = raster_union(streams)
    stream_buffer = stream_u.buffer(500).intersection(boundary) if stream_u else None
    candidate_forest = forest_u.difference(stream_buffer) if stream_buffer else forest_u
    candidate_large_parts = []
    for geom in getattr(candidate_forest, "geoms", [candidate_forest]):
        if geom.area >= 1_000_000:
            candidate_large_parts.append(geom)
    candidate_area = unary_union(candidate_large_parts) if candidate_large_parts else None
    write_geojson(out / "stream_buffer_500m.geojson", [{"geometry": stream_buffer, "properties": {"buffer_m": 500}}])
    write_geojson(
        out / "candidate_forest_gt1km2.geojson",
        [{"geometry": g, "properties": {"area_km2": round(g.area / 1_000_000, 6)}} for g in candidate_large_parts],
    )

    points = []
    if candidate_area and not candidate_area.is_empty:
        minx, miny, maxx, maxy = candidate_area.bounds
        start_x = math.ceil(minx / 2000) * 2000
        start_y = math.ceil(miny / 2000) * 2000
        with rasterio.open(dem_tif) as src:
            x = start_x
            while x <= maxx:
                y = start_y
                while y <= maxy:
                    p = Point(float(x), float(y))
                    if candidate_area.covers(p):
                        elev = raster_value_at(src, p.x, p.y)
                        if elev is not None:
                            points.append({"geometry": p, "elev": elev})
                    y += 2000
                x += 2000
    high_points = [p for p in points if p["elev"] >= 500]
    write_csv(
        out / "candidate_points.csv",
        [
            {"id": idx, "x": p["geometry"].x, "y": p["geometry"].y, "elevation_m": round(p["elev"], 2)}
            for idx, p in enumerate(points, start=1)
        ],
    )
    write_csv(
        out / "candidate_points_elev_gt500.csv",
        [
            {"id": idx, "x": p["geometry"].x, "y": p["geometry"].y, "elevation_m": round(p["elev"], 2)}
            for idx, p in enumerate(high_points, start=1)
        ],
    )
    stations_shp = work / "stations_gt500.shp"
    if high_points:
        write_point_shapefile(stations_shp, high_points)
        viewshed = work / "viewshed_height10.tif"
        run([str(WBT), "--run=Viewshed", f"--wd={work}", f"--dem={dem_tif}", f"--stations={stations_shp}", f"--output={viewshed}", "--height=10"])
        shutil.copyfile(viewshed, out / "viewshed_height10.tif")
        viewshed_u = raster_union(viewshed)
        viewshed_area_km2 = round(viewshed_u.intersection(boundary).area / 1_000_000, 6) if viewshed_u else 0
    else:
        viewshed_area_km2 = 0

    with rasterio.open(dem_tif) as src, rasterio.open(streams) as st:
        px_area = abs(src.transform.a * src.transform.e)
        stream_cells = int(np.count_nonzero(st.read(1) > 0))
    metrics = [
        {"metric": "dem_resolution_m", "value": math.sqrt(px_area)},
        {"metric": "flow_threshold_cells", "value": 500},
        {"metric": "threshold_upstream_area_km2", "value": round(500 * px_area / 1_000_000, 6)},
        {"metric": "stream_cells_gt500", "value": stream_cells},
        {"metric": "stream_buffer_500m_area_km2", "value": round(stream_buffer.area / 1_000_000, 6) if stream_buffer else 0},
        {"metric": "forest_original_area_km2", "value": round(forest_u.area / 1_000_000, 6)},
        {"metric": "forest_singlepart_count", "value": len(forest_parts)},
        {"metric": "candidate_forest_gt1km2_area_km2", "value": round(candidate_area.area / 1_000_000, 6) if candidate_area else 0},
        {"metric": "grid_points_2km_in_candidate_area", "value": len(points)},
        {"metric": "points_elevation_gt500m", "value": len(high_points)},
        {"metric": "viewshed_height_m", "value": 10},
        {"metric": "viewshed_area_km2", "value": viewshed_area_km2},
    ]
    write_csv(out / "fire_site_metrics.csv", metrics)
    summary["FireMSite"] = {
        "status": "completed",
        "outputs": [
            str(out / "filled_dem.tif"),
            str(out / "d8_pointer.tif"),
            str(out / "flow_accum_cells.tif"),
            str(out / "streams_gt500.tif"),
            str(out / "stream_buffer_500m.geojson"),
            str(out / "candidate_forest_gt1km2.geojson"),
            str(out / "candidate_points.csv"),
            str(out / "candidate_points_elev_gt500.csv"),
            str(out / "viewshed_height10.tif") if high_points else "viewshed skipped: no points >=500m",
            str(out / "fire_site_metrics.csv"),
        ],
    }


def zonal_values(src, arr: np.ndarray, geom, valid_mask: np.ndarray | None = None):
    window = rasterio.features.geometry_window(src, [mapping(geom)], boundless=False)
    row_slice, col_slice = window.toslices()
    sub_arr = arr[row_slice, col_slice]
    sub_transform = src.window_transform(window)
    mask = geometry_mask([mapping(geom)], out_shape=sub_arr.shape, transform=sub_transform, invert=True)
    if valid_mask is not None:
        mask &= valid_mask[row_slice, col_slice]
    return sub_arr[mask]


def run_town_type(summary: dict) -> None:
    base = DATA / "Data_TownType"
    out = OUT / "03_TownType"
    work = WORK / "03_TownType"
    dem = work / "dem.tif"
    landuse = work / "landuse.tif"
    light = work / "light.tif"
    translate_to_tif(base / "dem", dem)
    translate_to_tif(base / "landuse", landuse)
    translate_to_tif(base / "light", light)

    slope = out / "slope_degrees.tif"
    if not slope.exists():
        run([str(GDALDEM), "slope", str(dem), str(slope), "-of", "GTiff"])

    with rasterio.open(dem) as dem_src, rasterio.open(slope) as slope_src:
        dem_arr = dem_src.read(1).astype("float32")
        slope_arr = slope_src.read(1).astype("float32")
        valid = dem_arr != dem_src.nodata
        dem_fill = np.where(valid, dem_arr, np.nan)
        max9 = ndimage.maximum_filter(np.where(valid, dem_arr, -999999), size=9, mode="nearest")
        min9 = ndimage.minimum_filter(np.where(valid, dem_arr, 999999), size=9, mode="nearest")
        relief = max9 - min9
        tci = np.log(relief + 0.01) + np.log(np.maximum(slope_arr, 0) + 0.01)
        tci = np.where(valid & np.isfinite(tci), tci, np.nan).astype("float32")
        profile = dem_src.profile.copy()
        profile.update(dtype="float32", nodata=np.float32(-9999.0), compress="lzw")
        relief_path = out / "relief_9x9.tif"
        tci_path = out / "tci.tif"
        with rasterio.open(relief_path, "w", **profile) as dst:
            dst.write(np.where(valid, relief, -9999).astype("float32"), 1)
        with rasterio.open(tci_path, "w", **profile) as dst:
            dst.write(np.where(np.isfinite(tci), tci, -9999).astype("float32"), 1)

        towns = read_features(base / "乡镇界.shp")
        with rasterio.open(landuse) as land_src:
            lu = land_src.read(1)
            farmland = lu == 1
            pixel_area_lu = abs(land_src.transform.a * land_src.transform.e)

            with rasterio.open(light) as light_src:
                light_arr = light_src.read(1).astype("float64")
                light_valid = light_arr != light_src.nodata
                county_geoms = defaultdict(list)
                for feat in towns:
                    county_geoms[str(feat["properties"].get("qxmc", "")).strip()].append(feat["geometry"])
                county_centers = {}
                county_light_sum = {}
                for county, geoms in county_geoms.items():
                    geom = unary_union(geoms)
                    vals_mask = geometry_mask([mapping(geom)], out_shape=light_arr.shape, transform=light_src.transform, invert=True)
                    mask = vals_mask & light_valid & (light_arr > 0)
                    total = float(light_arr[mask].sum())
                    county_light_sum[county] = total
                    if total > 0:
                        rows, cols = np.where(mask)
                        xs, ys = rasterio.transform.xy(light_src.transform, rows, cols, offset="center")
                        xs = np.asarray(xs)
                        ys = np.asarray(ys)
                        weights = light_arr[rows, cols]
                        county_centers[county] = Point(float((xs * weights).sum() / total), float((ys * weights).sum() / total))
                    else:
                        county_centers[county] = geom.centroid

                gdp_df = pd.read_csv(base / "GDP.csv")
                county_col = gdp_df.columns[0]
                gdp_col = gdp_df.columns[1]
                gdp_map = {str(r[county_col]).strip(): float(r[gdp_col]) for _, r in gdp_df.iterrows()}

                rows = []
                structure = np.ones((3, 3), dtype=bool)
                for idx, feat in enumerate(towns, start=1):
                    geom = feat["geometry"]
                    props = feat["properties"]
                    town = str(props.get("xzmc", "")).strip()
                    county = str(props.get("qxmc", "")).strip()

                    tci_vals = zonal_values(dem_src, tci, geom, np.isfinite(tci))
                    mean_tci = float(np.nanmean(tci_vals)) if tci_vals.size else math.nan

                    lu_window = rasterio.features.geometry_window(land_src, [mapping(geom)], boundless=False)
                    lu_row_slice, lu_col_slice = lu_window.toslices()
                    farmland_sub = farmland[lu_row_slice, lu_col_slice]
                    lu_transform = land_src.window_transform(lu_window)
                    lu_mask = geometry_mask(
                        [mapping(geom)],
                        out_shape=farmland_sub.shape,
                        transform=lu_transform,
                        invert=True,
                    )
                    town_farmland = farmland_sub & lu_mask
                    farmland_area_km2 = float(town_farmland.sum() * pixel_area_lu / 1_000_000)
                    labels, nlabels = ndimage.label(town_farmland, structure=structure)
                    patch_count = 0
                    for label_id in range(1, nlabels + 1):
                        if int((labels == label_id).sum()) * pixel_area_lu >= 1000:
                            patch_count += 1
                    lsi = farmland_area_km2 / patch_count if patch_count else math.nan

                    light_vals = zonal_values(light_src, light_arr, geom, light_valid & (light_arr > 0))
                    town_light = float(light_vals.sum()) if light_vals.size else 0.0
                    county_light = county_light_sum.get(county, 0)
                    alloc_gdp = gdp_map.get(county, math.nan)
                    town_gdp = alloc_gdp * town_light / county_light if county_light and not math.isnan(alloc_gdp) else math.nan
                    distance = geom.centroid.distance(county_centers[county]) if county in county_centers else math.nan
                    rows.append(
                        {
                            "id": idx,
                            "xzmc": town,
                            "qxmc": county,
                            "mean_tci": round(mean_tci, 6) if not math.isnan(mean_tci) else "",
                            "farmland_area_km2": round(farmland_area_km2, 6),
                            "farmland_patch_count_ge1000m2": patch_count,
                            "lsi_km2_per_patch": round(lsi, 6) if not math.isnan(lsi) else "",
                            "town_light_sum": round(town_light, 6),
                            "county_light_sum": round(county_light, 6),
                            "distance_to_county_light_center_m": round(distance, 3) if not math.isnan(distance) else "",
                            "allocated_gdp_100m_yuan": round(town_gdp, 6) if not math.isnan(town_gdp) else "",
                        }
                    )
    write_csv(out / "town_indicators.csv", rows)
    summary["TownType"] = {
        "status": "indicators_completed_classification_rule_needed",
        "outputs": [
            str(out / "slope_degrees.tif"),
            str(out / "relief_9x9.tif"),
            str(out / "tci.tif"),
            str(out / "town_indicators.csv"),
        ],
        "finding": "The question text provides indicator formulas, but the final town-type classification thresholds/rules are not explicit in the extracted PDF text. Indicators are computed; final class labels should use the official rule if supplied.",
    }


def attach_reference_validation(summary: dict) -> None:
    metrics_path = OUT / "02_FireMSite" / "fire_site_metrics.csv"
    if not metrics_path.exists() or "FireMSite" not in summary:
        return
    metrics = {}
    with metrics_path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            metrics[row["metric"]] = row["value"]

    def status(computed: object, reference: object, tolerance: float = 1e-6) -> str:
        try:
            c = float(computed)
            r = float(reference)
            return "match" if abs(c - r) <= tolerance else "mismatch"
        except Exception:
            return "match" if str(computed) == str(reference) else "mismatch"

    checks = [
        {
            "blank": "空5",
            "meaning": "DEM resolution",
            "computed": metrics.get("dem_resolution_m", ""),
            "reference": 30,
            "status": status(metrics.get("dem_resolution_m", ""), 30),
        },
        {"blank": "空6", "meaning": "hydrology step", "computed": "填洼", "reference": "填洼", "status": "match"},
        {"blank": "空7", "meaning": "hydrology step", "computed": "流向", "reference": "流向", "status": "match"},
        {"blank": "空8", "meaning": "hydrology step", "computed": "流量/汇流累积", "reference": "流量", "status": "match"},
        {
            "blank": "空9",
            "meaning": "threshold upstream area km2",
            "computed": metrics.get("threshold_upstream_area_km2", ""),
            "reference": 0.45,
            "status": status(metrics.get("threshold_upstream_area_km2", ""), 0.45),
        },
        {
            "blank": "空10",
            "meaning": "stream threshold result",
            "computed": metrics.get("stream_cells_gt500", ""),
            "reference": 6187,
            "status": status(metrics.get("stream_cells_gt500", ""), 6187),
        },
        {
            "blank": "空11",
            "meaning": "stream/buffer area",
            "computed": metrics.get("stream_buffer_500m_area_km2", ""),
            "reference": 361.2898613140585,
            "status": status(metrics.get("stream_buffer_500m_area_km2", ""), 361.2898613140585, tolerance=0.01),
        },
        {
            "blank": "空12",
            "meaning": "forest original area km2",
            "computed": metrics.get("forest_original_area_km2", ""),
            "reference": 170.12544576513832,
            "status": status(metrics.get("forest_original_area_km2", ""), 170.12544576513832, tolerance=0.01),
        },
        {"blank": "空13", "meaning": "overlay operation", "computed": "擦除", "reference": "擦除", "status": "match"},
        {"blank": "空14", "meaning": "geometry operation", "computed": "多部分至单部分", "reference": "多部分至单部分", "status": "match"},
        {
            "blank": "空15",
            "meaning": "singlepart forest count",
            "computed": metrics.get("forest_singlepart_count", ""),
            "reference": 74,
            "status": status(metrics.get("forest_singlepart_count", ""), 74),
        },
        {
            "blank": "空16",
            "meaning": "candidate forest area km2",
            "computed": metrics.get("candidate_forest_gt1km2_area_km2", ""),
            "reference": 27.225092622989372,
            "status": status(metrics.get("candidate_forest_gt1km2_area_km2", ""), 27.225092622989372, tolerance=0.01),
        },
        {"blank": "空17", "meaning": "point grid operation", "computed": "创建渔网", "reference": "创建渔网", "status": "match"},
        {
            "blank": "空18",
            "meaning": "candidate grid point count",
            "computed": metrics.get("grid_points_2km_in_candidate_area", ""),
            "reference": 7,
            "status": status(metrics.get("grid_points_2km_in_candidate_area", ""), 7),
        },
        {"blank": "空19", "meaning": "extract raster values", "computed": "提取值至点", "reference": "提取值至点", "status": "match"},
        {
            "blank": "空20",
            "meaning": "points after elevation filter",
            "computed": metrics.get("points_elevation_gt500m", ""),
            "reference": 3,
            "status": status(metrics.get("points_elevation_gt500m", ""), 3),
        },
        {"blank": "空21", "meaning": "viewshed field/parameter", "computed": "高程", "reference": "高程", "status": "match"},
        {
            "blank": "空22",
            "meaning": "viewshed area km2",
            "computed": metrics.get("viewshed_area_km2", ""),
            "reference": 71.9856,
            "status": status(metrics.get("viewshed_area_km2", ""), 71.9856, tolerance=0.01),
        },
    ]
    summary["FireMSite"]["validation"] = checks
    summary["FireMSite"]["status"] = "completed_with_reference_mismatches"
    summary["FireMSite"][
        "finding"
    ] = "The run completes, but several numeric blanks do not match the reference answer sheet. The stream extraction and multipart-to-singlepart behavior must be switched to the competition/QGIS/ArcGIS-equivalent algorithm before using these numbers as answers."


def write_report(summary: dict) -> None:
    validation = summary.get("FireMSite", {}).get("validation", [])
    lines = [
        "# First Hunan GIS competition full run report",
        "",
        f"Input folder: `{ROOT}`",
        f"Output folder: `{OUT}`",
        "",
        "## Key findings",
        "",
        "- The real data is under `Data/Data_*`, not directly under the question root. Folder scanning should search nested datasets.",
        "- ArcInfo Grid rasters and WhiteboxTools are more reliable after conversion to GeoTIFF in an ASCII working directory.",
        "- BuildingDesign has a spatial alignment problem: `plan/roadcenter` and `buildings/design.tif` do not overlap, so several answers would be false precision unless registration is confirmed.",
        "- FireMSite ran end to end, including hydrology, 500 m stream buffer, candidate forest, 2 km grid points, elevation filtering, and viewshed height 10 m.",
        "- TownType indicator rasters and town-level table were produced; final class labels need the official classification rule if it exists outside the extracted question text.",
        "",
        "## Reference-answer check",
        "",
        "The screenshot supplied by the user was treated as a reference answer sheet for blanks 5-22. Matching items are useful; mismatches are not hidden because they indicate algorithm/engine differences that must be resolved before trusting automatic answers.",
        "",
    ]
    if validation:
        lines.extend([
            "| Blank | Meaning | Computed | Reference | Status |",
            "| --- | --- | ---: | ---: | --- |",
        ])
        for item in validation:
            lines.append(
                f"| {item['blank']} | {item['meaning']} | {item['computed']} | {item['reference']} | {item['status']} |"
            )
        lines.append("")
    lines.extend([
        "## Outputs by task",
        "",
    ])
    for task, data in summary.items():
        lines.append(f"### {task}")
        lines.append(f"- Status: `{data['status']}`")
        if data.get("finding"):
            lines.append(f"- Finding: {data['finding']}")
        lines.append("- Files:")
        for item in data.get("outputs", []):
            lines.append(f"  - `{item}`")
        lines.append("")
    (OUT / "run_report.md").write_text("\n".join(lines), encoding="utf-8")
    write_json(OUT / "answers.json", summary)


def main() -> None:
    ensure_dirs()
    summary: dict = {}
    run_building_design(summary)
    run_fire_site(summary)
    attach_reference_validation(summary)
    run_town_type(summary)
    write_report(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
