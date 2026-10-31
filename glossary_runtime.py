"""Use human-approved game terms to rank translation drafts, without rewriting text."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ApprovedTerm:
    ru: str
    kk_variants: tuple[str, ...]
    source_pattern: re.Pattern[str]


def load_approved_terms(path: Path | None) -> list[ApprovedTerm]:
    if path is None:
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    terms = []
    for row in rows:
        if row.get("reviewed_by_human", "").strip().casefold() != "true":
            continue
        if (row.get("use_for_ranking", "true").strip().casefold() or "true") != "true":
            continue
        kk = row.get("approved_kk", "").strip() or row.get("kk", "").strip()
        if not kk:
            raise ValueError(f"{row.get('ru', '')}: approved term needs Kazakh text")
        ru = row["ru"].strip()
        pattern = row.get("ru_search") or r"(?<!\w)" + re.escape(ru) + r"\w*"
        terms.append(ApprovedTerm(ru, tuple(v.strip() for v in kk.split("|") if v.strip()),
                                  re.compile(pattern, re.IGNORECASE)))
    return terms


def required_terms(source: str, terms: list[ApprovedTerm]) -> list[ApprovedTerm]:
    return [term for term in terms if term.source_pattern.search(source)]


def matched_term(candidate: str, term: ApprovedTerm) -> bool:
    return any(re.search(r"(?<!\w)" + re.escape(variant) + r"[\w-]*", candidate, re.IGNORECASE)
               for variant in term.kk_variants)


def rank_by_glossary(candidates: list[str], required: list[ApprovedTerm]) -> list[str]:
    return sorted(candidates, key=lambda candidate: -sum(matched_term(candidate, term) for term in required))
