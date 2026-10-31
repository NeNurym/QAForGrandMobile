#!/usr/bin/env python3
"""Draft game translations with a local Kazakh Qwen server and a term list.

All outputs are unverified suggestions. The script never writes ARB or human flags.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.request
from pathlib import Path

from locqa import placeholders, read_arb
from model_proposals import TAG


FIELDS = ["key", "source", "english_context", "original_kk", "qwen_kk", "used_terms",
          "glossary_status", "warning"]
SYSTEM = ("Ты переводчик интерфейса мобильной игры Grand Mobile. Переводи с русского на "
          "естественный казахский кириллицей. Учитывай игровой смысл и краткость UI. "
          "Сохраняй плейсхолдеры в фигурных скобках, HTML-теги, числа и имена брендов точно. "
          "Не добавляй объяснений, кавычек или комментариев: ответь только переводом.")


def load_terms(path: Path, include_drafts: bool = False) -> list[dict[str, object]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    terms = []
    for row in rows:
        approved = row.get("reviewed_by_human", "").strip().casefold() == "true"
        if not approved and not include_drafts:
            continue
        kk = row.get("approved_kk", "").strip() if approved else row.get("kk_draft", "").strip()
        if not kk:
            continue
        ru = row["ru"].strip()
        pattern = row.get("ru_search", "").strip() or r"(?<!\w)" + re.escape(ru) + r"\w*"
        terms.append({"ru": ru, "kk": kk, "approved": approved,
                      "strict": row.get("use_for_ranking", "true").strip().casefold() != "false",
                      "alternatives": row.get("kk_alternatives", "").strip() if not approved else "",
                      "pattern": re.compile(pattern, re.IGNORECASE)})
    return terms


def terms_for_source(source: str, terms: list[dict[str, object]], limit: int = 8) -> list[dict[str, object]]:
    matched = [term for term in terms if term["pattern"].search(source)]
    # More specific phrases come first; avoid crowding the prompt with overlapping lemmas.
    matched.sort(key=lambda term: -len(str(term["ru"])))
    return matched[:limit]


def build_prompt(key: str, source: str, english: str, terms: list[dict[str, object]]) -> str:
    parts = [f"Ключ интерфейса: {key}"]
    if english and english != source:
        parts.append("Английский контекст: " + english[:500])
    strict = [term for term in terms if term["strict"]]
    contextual = [term for term in terms if not term["strict"]]
    if strict:
        label = "Утверждённые игровые термины" if all(term["approved"] for term in strict) else "Черновые игровые термины (проверяются носителями)"
        parts.append(label + ": " + "; ".join(f"{term['ru']} = {term['kk']}" for term in strict))
    if contextual:
        choices = [f"{term['ru']}: " + " / ".join([str(term["kk"])] + [v for v in str(term["alternatives"]).split("|") if v])
                   for term in contextual]
        parts.append("Неоднозначные игровые слова; выбери естественный вариант по контексту: " + "; ".join(choices))
    parts.append("Русский текст: " + source)
    parts.append("Казахский перевод:")
    return "\n".join(parts)


def structurally_safe(source: str, candidate: str) -> bool:
    return (bool(candidate.strip()) and placeholders(source) == placeholders(candidate)
            and TAG.findall(source) == TAG.findall(candidate)
            and re.findall(r"\d+", source) == re.findall(r"\d+", candidate))


def contains_kazakh_term(candidate: str, term: str) -> bool:
    lower_candidate = candidate.casefold()
    lower_term = term.casefold()
    if lower_term in lower_candidate:
        return True
    # Verbal noun -у may become a conjugated verb: жақсарту → жақсарттыңыз.
    return bool(" " not in lower_term and lower_term.endswith("у") and len(lower_term) >= 5
                and lower_term[:-1] in lower_candidate)


def complete(server: str, prompt: str, max_tokens: int) -> tuple[str, str]:
    payload = {"model": "local", "messages": [{"role": "system", "content": SYSTEM},
                                               {"role": "user", "content": prompt}],
               "temperature": 0, "max_tokens": max_tokens}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(server.rstrip("/") + "/v1/chat/completions", data=data,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.load(response)
    choice = result["choices"][0]
    return choice["message"]["content"].strip().strip('"“”'), choice.get("finish_reason", "")


def generate(corrections: Path, english_arb: Path, glossary: Path, output: Path,
             server: str = "http://127.0.0.1:8087", include_drafts: bool = False,
             limit: int | None = None) -> tuple[int, int]:
    with corrections.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if limit is not None:
        rows = rows[:limit]
    english_values = read_arb(english_arb)[2]
    terms = load_terms(glossary, include_drafts)
    output_rows = []
    valid = 0
    for index, row in enumerate(rows, 1):
        source = row["source"]
        english = str(english_values.get(row["key"], ""))
        selected = terms_for_source(source, terms)
        prompt = build_prompt(row["key"], source, english, selected)
        max_tokens = min(400, max(64, len(source) // 2 + 40))
        candidate, finish_reason = complete(server, prompt, max_tokens)
        warning = ""
        if finish_reason == "length":
            warning = "Rejected: model response was truncated"
            candidate = ""
        elif not structurally_safe(source, candidate):
            warning = "Rejected: placeholders, HTML tags or numbers changed"
            candidate = ""
        else:
            valid += 1
            missing = [str(term["ru"]) for term in selected if term["strict"]
                       if not contains_kazakh_term(candidate, str(term["kk"]))]
            if missing:
                warning = "Check glossary forms: " + ", ".join(missing)
        output_rows.append({"key": row["key"], "source": source, "english_context": english,
                            "original_kk": row["target"], "qwen_kk": candidate,
                            "used_terms": "; ".join(f"{term['ru']}={term['kk']}{' (контекст)' if not term['strict'] else ''}" for term in selected),
                            "glossary_status": "draft" if any(not term["approved"] for term in selected) else "approved" if selected else "none",
                            "warning": warning})
        if index % 20 == 0:
            print(f"Prepared {index}/{len(rows)}", flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(output_rows)
    return len(rows), valid


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("corrections", "english-arb", "glossary", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--server", default="http://127.0.0.1:8087")
    parser.add_argument("--include-drafts", action="store_true", help="Experiment with unapproved glossary drafts")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    rows, valid = generate(args.corrections, args.english_arb, args.glossary, args.out,
                           args.server, args.include_drafts, args.limit)
    print(f"Saved {valid}/{rows} structurally valid, unverified translations to {args.out}")


if __name__ == "__main__":
    main()
