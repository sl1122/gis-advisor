from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


DEFAULT_QGIS_ROOTS = [
    Path(r"D:\QGIS"),
    Path(r"C:\Program Files\QGIS 3.44.11"),
    Path(r"C:\Program Files\QGIS 3.44"),
    Path(r"C:\OSGeo4W"),
]


@dataclass(frozen=True)
class GeoEnvironment:
    qgis_root: str | None
    qgis_process: str | None
    gdalinfo: str | None
    ogrinfo: str | None
    grass: str | None
    whitebox_tools: str | None
    qgis_version: str | None
    gdal_version: str | None
    grass_version: str | None
    whitebox_version: str | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "qgis_root": self.qgis_root,
            "qgis_process": self.qgis_process,
            "gdalinfo": self.gdalinfo,
            "ogrinfo": self.ogrinfo,
            "grass": self.grass,
            "whitebox_tools": self.whitebox_tools,
            "qgis_version": self.qgis_version,
            "gdal_version": self.gdal_version,
            "grass_version": self.grass_version,
            "whitebox_version": self.whitebox_version,
        }


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _run_version(command: str, args: list[str], timeout: int = 30) -> str | None:
    try:
        completed = subprocess.run(
            [command, *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (completed.stdout or completed.stderr).strip()
    return text.splitlines()[0] if text else None


def _find_in_qgis_root(root: Path, names: list[str]) -> str | None:
    candidates = [root / "bin" / name for name in names]
    found = _first_existing(candidates)
    return str(found) if found else None


def _find_whitebox_tools() -> str | None:
    direct = shutil.which("whitebox_tools")
    if direct:
        return direct
    try:
        import whitebox
    except ImportError:
        return None
    package_dir = Path(whitebox.__file__).resolve().parent
    candidates = [
        package_dir / "whitebox_tools.exe",
        package_dir / "WBT" / "whitebox_tools.exe",
        package_dir / "whitebox_tools",
        package_dir / "WBT" / "whitebox_tools",
    ]
    found = _first_existing(candidates)
    return str(found) if found else None


def detect_environment() -> GeoEnvironment:
    qgis_process = shutil.which("qgis_process") or shutil.which("qgis_process-qgis-ltr")
    gdalinfo = shutil.which("gdalinfo")
    ogrinfo = shutil.which("ogrinfo")
    grass = shutil.which("grass") or shutil.which("grass84")
    whitebox_tools = _find_whitebox_tools()

    qgis_root: Path | None = None
    for root in DEFAULT_QGIS_ROOTS:
        if root.exists():
            qgis_root = root
            break

    if qgis_root:
        qgis_process = qgis_process or _find_in_qgis_root(qgis_root, ["qgis_process-qgis-ltr.bat", "qgis_process.exe"])
        gdalinfo = gdalinfo or _find_in_qgis_root(qgis_root, ["gdalinfo.exe"])
        ogrinfo = ogrinfo or _find_in_qgis_root(qgis_root, ["ogrinfo.exe"])
        grass = grass or _find_in_qgis_root(qgis_root, ["grass84.bat", "grass83.bat", "grass.bat"])

    return GeoEnvironment(
        qgis_root=str(qgis_root) if qgis_root else None,
        qgis_process=qgis_process,
        gdalinfo=gdalinfo,
        ogrinfo=ogrinfo,
        grass=grass,
        qgis_version=_run_version(qgis_process, ["--version"]) if qgis_process else None,
        gdal_version=_run_version(gdalinfo, ["--version"]) if gdalinfo else None,
        grass_version=_run_version(grass, ["--version"]) if grass else None,
        whitebox_tools=whitebox_tools,
        whitebox_version=_run_version(whitebox_tools, ["--version"]) if whitebox_tools else None,
    )
