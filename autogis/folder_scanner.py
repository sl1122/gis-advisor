from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree


QUESTION_EXTENSIONS = {".txt", ".md", ".html", ".htm", ".pdf", ".docx"}
DOCUMENT_EXTENSIONS = QUESTION_EXTENSIONS | {".doc", ".docx", ".pdf"}
RASTER_EXTENSIONS = {".tif", ".tiff", ".img", ".vrt", ".asc", ".jp2"}
VECTOR_EXTENSIONS = {".shp", ".gpkg", ".geojson", ".json", ".kml"}
TABLE_EXTENSIONS = {".csv", ".xls", ".xlsx", ".dbf"}

QUESTION_HINTS = ["question", "task", "readme", "requirement", "note", "problem", "ti", "timu"]
DEM_HINTS = ["dem", "dsm", "dtm", "elevation", "gaocheng", "height"]
BOUNDARY_HINTS = ["boundary", "mask", "clip", "region", "area", "study", "extent"]
RS_HINTS = ["landsat", "sentinel", "modis", "remote", "band", "ndvi", "ndwi"]
HYDRO_HINTS = ["river", "stream", "water", "basin", "watershed", "flow"]
ANSWER_HINTS = ["answer", "result", "template", "submit"]

QUESTION_CJK_HINTS = ["\u9898", "\u8bd5\u9898", "\u4efb\u52a1", "\u8981\u6c42", "\u8bf4\u660e", "\u9898\u76ee"]
DEM_CJK_HINTS = ["\u9ad8\u7a0b", "\u6570\u5b57\u9ad8\u7a0b", "\u5761\u5ea6", "\u5761\u5411"]
BOUNDARY_CJK_HINTS = ["\u8fb9\u754c", "\u8303\u56f4", "\u7814\u7a76\u533a", "\u4e61\u9547\u754c"]
RS_CJK_HINTS = ["\u9065\u611f", "\u6ce2\u6bb5"]
HYDRO_CJK_HINTS = ["\u6cb3", "\u6c34\u7cfb", "\u6d41\u57df"]
ANSWER_CJK_HINTS = ["\u7b54\u5377", "\u7b54\u6848", "\u63d0\u4ea4"]

INTERNAL_DIR_NAMES = {"info", "__macosx"}
ALWAYS_INTERNAL_SUFFIXES = {
    ".adf",
    ".nit",
    ".dir",
    ".lock",
    ".ovr",
    ".tfw",
    ".jgw",
    ".rrd",
    ".aux",
    ".cpg",
    ".prj",
    ".sbn",
    ".sbx",
    ".shx",
}
SHAPEFILE_SIDECARS = {".dbf", ".shx", ".prj", ".sbn", ".sbx", ".cpg", ".qix", ".fix"}
COMPOUND_INTERNAL_SUFFIXES = (".aux.xml", ".shp.xml", ".tif.xml", ".tiff.xml")


class _HTMLTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)


@dataclass
class ScannedFile:
    path: Path
    role: str
    kind: str
    confidence: float
    reason: str
    size: int
    preview: str | None = None

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "name": self.path.name,
            "role": self.role,
            "kind": self.kind,
            "confidence": self.confidence,
            "reason": self.reason,
            "size": self.size,
            "preview": self.preview,
        }


@dataclass
class FolderScan:
    root: Path
    files: list[ScannedFile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        role_groups: dict[str, list[dict]] = {}
        for item in self.files:
            role_groups.setdefault(item.role, []).append(item.to_dict())
        questions = [item.to_dict() for item in self.files if item.role == "question"]
        return {
            "ok": True,
            "root": str(self.root),
            "warnings": self.warnings,
            "counts": {
                "total": len(self.files),
                **{role: len(items) for role, items in role_groups.items()},
            },
            "groups": role_groups,
            "question_candidates": questions,
            "suggested": {
                "question": _first_path(self.files, "question"),
                "dem": _first_path(self.files, "dem"),
                "boundary": _first_path(self.files, "boundary"),
                "primary_raster": _first_path(self.files, "raster"),
                "primary_vector": _first_path(self.files, "vector"),
                "task_text": _best_question_text(self.files),
            },
        }


def _first_path(files: list[ScannedFile], role: str) -> str | None:
    candidates = [item for item in files if item.role == role]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item.confidence, reverse=True)
    return str(candidates[0].path)


def _best_question_text(files: list[ScannedFile]) -> str | None:
    candidates = [item for item in files if item.role == "question" and item.preview]
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item.confidence, len(item.preview or "")), reverse=True)
    return candidates[0].preview


def _contains_hint(name: str, hints: list[str]) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in hints)


def _contains_cjk_hint(name: str, hints: list[str]) -> bool:
    return any(hint in name for hint in hints)


def _normalize_document_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


FORMULA_HINTS = [
    "=", "＞", "＜", "≥", "≤", ">=", "<=", "×", "÷", "+", "-", "/", "^", "%",
    "公式", "计算", "空地率", "容积率", "建筑密度", "绿地率", "坡度", "坡向", "指数", "NDVI", "NDBI", "TWI",
    "面积", "长度", "距离", "密度", "比例", "均值", "总和", "权重", "得分", "适宜性",
]


def _looks_like_formula_line(line: str) -> bool:
    compact = re.sub(r"\s+", "", line)
    if len(compact) < 4 or len(compact) > 180:
        return False
    if "@" in compact or any(word in compact for word in ["邮件", "E-mail", "email", "附件", "提交"]):
        return False
    if any(word in compact for word in ["指北针", "图例", "比例尺", "图名"]) and not re.search(r"[=＝]", compact):
        return False
    if re.search(r"[\u4e00-\u9fffA-Za-z0-9_()（）]+[=＝][\u4e00-\u9fffA-Za-z0-9_().（）+\-*/×÷^%]+", compact):
        return True
    if any(word in compact for word in ["按式", "公式", "计算", "比率", "指数", "权重", "得分"]):
        return True
    if any(symbol in compact for symbol in ["≥", "≤", ">=", "<=", "＞", "＜"]) and re.search(r"\d", compact):
        return True
    if any(word in compact for word in ["阈值", "面积需", "建设高度", "观察高度", "目标高度"]) and re.search(r"\d", compact):
        return True
    return False


def _extract_formula_lines(text: str, max_items: int = 18) -> list[str]:
    formulas: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or not _looks_like_formula_line(line):
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        formulas.append(line)
        if len(formulas) >= max_items:
            break
    return formulas


def _format_document_preview(raw_text: str, limit: int) -> str | None:
    normalized = _normalize_document_text(raw_text)
    if not normalized:
        return None
    formulas = _extract_formula_lines(raw_text)
    if formulas:
        formula_block = "【疑似公式/计算关系】\n" + "\n".join(f"- {item}" for item in formulas)
        normalized = f"{formula_block}\n\n【正文摘录】\n{normalized}"
    return normalized[:limit] if normalized else None


def _read_pdf_with_pdfplumber(path: Path, limit: int) -> str | None:
    try:
        import pdfplumber
    except ImportError:
        return None
    try:
        parts: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:12]:
                text = page.extract_text(layout=True, x_tolerance=1, y_tolerance=3) or ""
                if text.strip():
                    parts.append(text)
                for table in page.extract_tables()[:3]:
                    rows = ["\t".join((cell or "").strip() for cell in row) for row in table if row]
                    if rows:
                        parts.append("【表格片段】\n" + "\n".join(rows[:20]))
                if sum(len(part) for part in parts) >= limit * 2:
                    break
    except Exception:
        return None
    return "\n".join(parts).strip() or None


def _read_pdf_with_pypdf(path: Path, limit: int) -> str | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages[:12]:
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text)
            if sum(len(part) for part in parts) >= limit * 2:
                break
    except Exception:
        return None
    return "\n".join(parts).strip() or None


def _read_pdf_preview(path: Path, limit: int) -> str | None:
    raw_text = _read_pdf_with_pdfplumber(path, limit) or _read_pdf_with_pypdf(path, limit)
    return _format_document_preview(raw_text, limit) if raw_text else None


def _read_docx_preview(path: Path, limit: int) -> str | None:
    try:
        with zipfile.ZipFile(path) as docx:
            raw = docx.read("word/document.xml")
    except (OSError, KeyError, zipfile.BadZipFile):
        return None
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return None
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    parts = [node.text or "" for node in root.iter(f"{namespace}t")]
    return _format_document_preview("".join(parts), limit)


def _read_preview(path: Path, limit: int = 12000) -> str | None:
    if path.suffix.lower() not in QUESTION_EXTENSIONS:
        return None
    if path.suffix.lower() == ".pdf":
        return _read_pdf_preview(path, limit)
    if path.suffix.lower() == ".docx":
        return _read_docx_preview(path, limit)
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if path.suffix.lower() in {".html", ".htm"}:
        parser = _HTMLTextParser()
        parser.feed(raw)
        raw = "\n".join(parser.parts)
    return _format_document_preview(raw, limit)


def _safe_size(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())
    except OSError:
        return 0


def _is_arcinfo_grid_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    names = {child.name.lower() for child in path.iterdir()}
    return "hdr.adf" in names and ("w001001.adf" in names or "dblbnd.adf" in names)


def _has_internal_parent(path: Path) -> bool:
    return any(part.lower() in INTERNAL_DIR_NAMES for part in path.parts)


def _is_below(path: Path, parents: set[Path]) -> bool:
    return any(parent == path or parent in path.parents for parent in parents)


def _is_internal_file(path: Path) -> bool:
    lowered = path.name.lower()
    if lowered.endswith(COMPOUND_INTERNAL_SUFFIXES):
        return True
    suffix = path.suffix.lower()
    if suffix in ALWAYS_INTERNAL_SUFFIXES:
        return True
    if suffix in SHAPEFILE_SIDECARS and path.with_suffix(".shp").exists():
        return True
    return False


def _classify_arcinfo_grid(path: Path) -> tuple[str, str, float, str]:
    name = path.name
    if _contains_hint(name, DEM_HINTS) or _contains_cjk_hint(name, DEM_CJK_HINTS):
        return "dem", "raster", 0.94, "ArcInfo Grid DEM/elevation raster dataset"
    if _contains_hint(name, RS_HINTS) or _contains_cjk_hint(name, RS_CJK_HINTS):
        return "remote_sensing", "raster", 0.82, "ArcInfo Grid remote-sensing raster dataset"
    return "raster", "raster", 0.72, "ArcInfo Grid raster dataset"


def _classify(path: Path) -> tuple[str, str, float, str]:
    suffix = path.suffix.lower()
    name = path.name

    if suffix in DOCUMENT_EXTENSIONS and (
        _contains_hint(name, ANSWER_HINTS) or _contains_cjk_hint(name, ANSWER_CJK_HINTS)
    ):
        return "document", "document", 0.72, "Likely answer/template document"
    if suffix in DOCUMENT_EXTENSIONS and (
        _contains_hint(name, QUESTION_HINTS) or _contains_cjk_hint(name, QUESTION_CJK_HINTS)
    ):
        return "question", "document", 0.92, "Likely task/question document"
    if suffix in DOCUMENT_EXTENSIONS:
        return "document", "document", 0.55, "Document file"

    if suffix in RASTER_EXTENSIONS and (
        _contains_hint(name, DEM_HINTS) or _contains_cjk_hint(name, DEM_CJK_HINTS)
    ):
        return "dem", "raster", 0.92, "Likely DEM/elevation raster"
    if suffix in VECTOR_EXTENSIONS and (
        _contains_hint(name, BOUNDARY_HINTS) or _contains_cjk_hint(name, BOUNDARY_CJK_HINTS)
    ):
        return "boundary", "vector", 0.86, "Likely study-area boundary"
    if suffix in RASTER_EXTENSIONS and (
        _contains_hint(name, RS_HINTS) or _contains_cjk_hint(name, RS_CJK_HINTS)
    ):
        return "remote_sensing", "raster", 0.82, "Likely remote-sensing raster"
    if suffix in VECTOR_EXTENSIONS and (
        _contains_hint(name, HYDRO_HINTS) or _contains_cjk_hint(name, HYDRO_CJK_HINTS)
    ):
        return "hydro_vector", "vector", 0.78, "Likely hydro vector layer"

    if suffix in RASTER_EXTENSIONS:
        return "raster", "raster", 0.62, "Raster dataset"
    if suffix in VECTOR_EXTENSIONS:
        return "vector", "vector", 0.62, "Vector dataset"
    if suffix in TABLE_EXTENSIONS:
        return "table", "table", 0.65, "Table dataset"

    return "other", "other", 0.25, "Unrecognized file type"


def scan_folder(root: Path, max_files: int = 500) -> FolderScan:
    root = root.expanduser().resolve()
    if not root.exists():
        scan = FolderScan(root=root)
        scan.warnings.append("Folder does not exist")
        return scan
    if not root.is_dir():
        scan = FolderScan(root=root)
        scan.warnings.append("Path is not a folder")
        return scan

    scan = FolderScan(root=root)
    arcgrid_dirs: set[Path] = set()

    for path in root.rglob("*"):
        if path.name.startswith(".") or _has_internal_parent(path):
            continue
        if _is_arcinfo_grid_dir(path):
            role, kind, confidence, reason = _classify_arcinfo_grid(path)
            scan.files.append(
                ScannedFile(
                    path=path,
                    role=role,
                    kind=kind,
                    confidence=confidence,
                    reason=reason,
                    size=_safe_size(path),
                )
            )
            arcgrid_dirs.add(path)

    count = len(scan.files)
    for path in root.rglob("*"):
        if count >= max_files:
            scan.warnings.append(f"Stopped after {max_files} data items")
            break
        if not path.is_file() or path.name.startswith("."):
            continue
        if _has_internal_parent(path) or _is_below(path, arcgrid_dirs) or _is_internal_file(path):
            continue
        role, kind, confidence, reason = _classify(path)
        if role == "other":
            continue
        preview = _read_preview(path) if role in {"question", "document"} else None
        scan.files.append(
            ScannedFile(
                path=path,
                role=role,
                kind=kind,
                confidence=confidence,
                reason=reason,
                size=_safe_size(path),
                preview=preview,
            )
        )
        count += 1

    scan.files.sort(key=lambda item: (item.role, -item.confidence, item.path.name.lower()))
    if any(item.role == "question" and not item.preview for item in scan.files):
        scan.warnings.append("题目文档已识别，但没有提取到正文。常见原因是扫描版 PDF、加密 PDF、图片题面，或 DOCX 结构异常。请复制题目文字到输入框，或先转成可选中文本 PDF。")
    return scan
