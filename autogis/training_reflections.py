from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = Path(r"D:\桌面\训练反思\source")
INDEX_PATH = ROOT / ".autogis" / "training_reflection_index.json"


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    tokens = set(re.findall(r"[a-zA-Z0-9_]+", lowered))
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for size in (2, 3, 4):
            tokens.update(chunk[i : i + size] for i in range(max(0, len(chunk) - size + 1)))
    return tokens


def _clean(text: str) -> str:
    text = re.sub(r"`{1,3}", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def rebuild_training_index(source_dir: Path = SOURCE_DIR) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not source_dir.exists():
        return records
    for path in sorted(source_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        chunks = re.split(r"(?m)^#{1,3}\s+", text)
        for index, chunk in enumerate(chunks):
            chunk = _clean(chunk)
            if len(chunk) < 60:
                continue
            title = chunk.split(" ", 1)[0][:80] or path.stem
            records.append(
                {
                    "id": f"{path.stem}:{index}",
                    "source": str(path),
                    "file": path.name,
                    "title": title,
                    "text": chunk[:1200],
                    "tokens": sorted(_tokens(f"{path.stem} {chunk[:1200]}")),
                }
            )
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return records


def _load_index() -> list[dict[str, Any]]:
    if not INDEX_PATH.exists():
        return rebuild_training_index()
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return rebuild_training_index()
    return data if isinstance(data, list) else []


def search_training_reflections(query: str, limit: int = 5, min_score: float = 0.04) -> list[dict[str, Any]]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in _load_index():
        item_tokens = set(item.get("tokens") or [])
        if not item_tokens:
            continue
        overlap = len(query_tokens & item_tokens)
        if not overlap:
            continue
        score = overlap / max(1, min(len(query_tokens), 80))
        if score >= min_score:
            scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "score": round(score, 3),
            "file": item.get("file"),
            "title": item.get("title"),
            "source": item.get("source"),
            "snippet": item.get("text", "")[:260],
        }
        for score, item in scored[:limit]
    ]
