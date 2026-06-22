from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
KNOWLEDGE_PATH = ROOT / "knowledge_base.json"


@dataclass
class KnowledgeMatch:
    id: str
    title: str
    category: str
    score: float
    matched_keywords: list[str] = field(default_factory=list)
    arcgis_path: str = ""
    qgis_path: str = ""
    steps: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "score": self.score,
            "matched_keywords": self.matched_keywords,
            "arcgis_path": self.arcgis_path,
            "qgis_path": self.qgis_path,
            "steps": self.steps,
            "checks": self.checks,
        }


@dataclass
class AntiPatternHit:
    id: str
    wrong_category: str
    matched_keywords: list[str]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "wrong_category": self.wrong_category,
            "matched_keywords": self.matched_keywords,
            "message": self.message,
        }


@dataclass
class KnowledgeReport:
    version: str
    matches: list[KnowledgeMatch]
    anti_patterns: list[AntiPatternHit]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "matches": [item.to_dict() for item in self.matches],
            "anti_patterns": [item.to_dict() for item in self.anti_patterns],
        }


def load_knowledge_base() -> dict[str, Any]:
    return json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))


def _hits(text: str, words: list[str]) -> list[str]:
    lowered = text.lower()
    return [word for word in words if word.lower() in lowered]


def _blocked_by_negative(text: str, negatives: list[str]) -> bool:
    return bool(_hits(text, negatives))


def match_knowledge(task: str, limit: int = 6) -> KnowledgeReport:
    data = load_knowledge_base()
    task = task or ""
    matches: list[KnowledgeMatch] = []
    anti_hits: list[AntiPatternHit] = []

    for item in data.get("anti_patterns", []):
        matched = _hits(task, item.get("when_keywords") or [])
        unless = _hits(task, item.get("unless_keywords") or [])
        if matched and not unless:
            anti_hits.append(
                AntiPatternHit(
                    id=item["id"],
                    wrong_category=item.get("wrong_category", ""),
                    matched_keywords=matched,
                    message=item.get("message", ""),
                )
            )

    blocked_categories = {item.wrong_category for item in anti_hits}
    for card in data.get("cards", []):
        positives = card.get("positive_keywords") or []
        matched = _hits(task, positives)
        if not matched:
            continue
        category = card.get("category", "")
        if category in blocked_categories and len(matched) < 2:
            continue
        if _blocked_by_negative(task, card.get("negative_keywords") or []) and len(matched) < 2:
            continue
        base = float(card.get("confidence") or 0.6)
        score = min(0.98, base + 0.04 * max(0, len(matched) - 1))
        matches.append(
            KnowledgeMatch(
                id=card["id"],
                title=card.get("title", card["id"]),
                category=category,
                score=round(score, 3),
                matched_keywords=matched,
                arcgis_path=card.get("arcgis_path", ""),
                qgis_path=card.get("qgis_path", ""),
                steps=card.get("steps") or [],
                checks=card.get("checks") or [],
            )
        )

    matches.sort(key=lambda item: (-item.score, item.category, item.title))
    return KnowledgeReport(version=data.get("version", ""), matches=matches[:limit], anti_patterns=anti_hits)


def run_regression_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    ok = True
    for case in cases:
        report = match_knowledge(case.get("task", ""), limit=12)
        categories = {item.category for item in report.matches}
        forbidden = set(case.get("forbid_categories") or [])
        required = set(case.get("require_categories") or [])
        failed = bool(categories & forbidden) or not required.issubset(categories)
        ok = ok and not failed
        results.append(
            {
                "name": case.get("name", ""),
                "ok": not failed,
                "categories": sorted(categories),
                "required_missing": sorted(required - categories),
                "forbidden_present": sorted(categories & forbidden),
                "anti_patterns": [item.to_dict() for item in report.anti_patterns],
            }
        )
    return {"ok": ok, "results": results}
