from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .env import detect_environment


RASTER_EXTENSIONS = {".tif", ".tiff", ".img", ".vrt", ".asc", ".jp2"}
VECTOR_EXTENSIONS = {".shp", ".gpkg", ".geojson", ".json", ".kml", ".gdb"}


def _run_json(command: str, args: list[str]) -> dict:
    completed = subprocess.run(
        [command, *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if completed.returncode != 0:
        return {
            "ok": False,
            "command": [command, *args],
            "stderr": completed.stderr.strip(),
            "stdout": completed.stdout.strip(),
        }
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "command": [command, *args],
            "stdout": completed.stdout.strip(),
        }
    payload["ok"] = True
    return payload


def _summarize_raster(path: Path, raw: dict) -> dict:
    size = raw.get("size", [])
    bands = raw.get("bands", [])
    coord = raw.get("coordinateSystem", {})
    geo_transform = raw.get("geoTransform")
    return {
        "ok": raw.get("ok", False),
        "path": str(path),
        "kind": "raster",
        "driver": raw.get("driverShortName"),
        "size": {"width": size[0], "height": size[1]} if len(size) >= 2 else None,
        "band_count": len(bands),
        "crs": coord.get("wkt") or coord.get("projjson", {}).get("name"),
        "geo_transform": geo_transform,
        "corner_coordinates": raw.get("cornerCoordinates"),
        "bands": [
            {
                "band": band.get("band"),
                "type": band.get("type"),
                "no_data": band.get("noDataValue"),
                "color_interpretation": band.get("colorInterpretation"),
            }
            for band in bands
        ],
    }


def _summarize_vector(path: Path, raw: dict) -> dict:
    layers = raw.get("layers", [])
    summary_layers = []
    for layer in layers:
        fields = layer.get("fields", [])
        geometry_fields = layer.get("geometryFields", [])
        summary_layers.append(
            {
                "name": layer.get("name"),
                "feature_count": layer.get("featureCount"),
                "geometry_fields": geometry_fields,
                "fields": [{"name": f.get("name"), "type": f.get("type")} for f in fields],
                "extent": layer.get("extent"),
            }
        )
    return {
        "ok": raw.get("ok", False),
        "path": str(path),
        "kind": "vector",
        "driver": raw.get("driverShortName") or raw.get("driverLongName"),
        "layers": summary_layers,
    }


def inspect_dataset(path: Path) -> dict:
    env = detect_environment()
    if not path.exists():
        return {"ok": False, "path": str(path), "error": "Path does not exist."}

    suffix = path.suffix.lower()
    is_arcinfo_grid = path.is_dir() and (path / "hdr.adf").exists()
    if (suffix in RASTER_EXTENSIONS or is_arcinfo_grid) and env.gdalinfo:
        raw = _run_json(env.gdalinfo, ["-json", str(path)])
        return _summarize_raster(path, raw) if raw.get("ok") else raw

    if suffix in VECTOR_EXTENSIONS and env.ogrinfo:
        raw = _run_json(env.ogrinfo, ["-json", "-so", str(path)])
        return _summarize_vector(path, raw) if raw.get("ok") else raw

    return {
        "ok": False,
        "path": str(path),
        "error": f"Unsupported or unknown dataset extension: {suffix}",
    }
