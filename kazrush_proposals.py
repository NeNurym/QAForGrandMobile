#!/usr/bin/env python3
"""Draft Russian-to-Kazakh review options with the local kazRush model."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from model_proposals import useful_model_candidate
from locqa import placeholders
from glossary_runtime import load_approved_terms, matched_term, rank_by_glossary, required_terms


FIELDS = ["key", "source", "original_kk", "kazrush_1", "kazrush_2", "kazrush_3",
          "approved_glossary_terms", "warning"]
TAG = re.compile(r"<[^>]+>")


def eligible(source: str) -> bool:
    return (bool(source.strip()) and not placeholders(source) and not TAG.search(source)
            and not source.endswith(" "))


def generate(corrections: Path, model_dir: Path, output: Path, limit: int | None = None,
             glossary: Path | None = None) -> tuple[int, int]:
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    with corrections.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if limit is not None:
        rows = rows[:limit]
    torch.set_num_threads(min(6, torch.get_num_threads()))
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True, use_fast=False, legacy=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_dir, local_files_only=True).eval()
    approved_terms = load_approved_terms(glossary)
    output_rows = []
    translated = 0
    for index, row in enumerate(rows, 1):
        source = row["source"]
        required = required_terms(source, approved_terms)
        candidates: list[str] = []
        warning = ""
        if eligible(source):
            inputs = tokenizer(source, return_tensors="pt", truncation=True, max_length=480)
            with torch.inference_mode():
                beams = model.generate(**inputs, num_beams=8 if required else 6,
                                       num_return_sequences=8 if required else 3,
                                       max_new_tokens=min(180, max(20, len(source) // 2 + 15)),
                                       early_stopping=True)
            for candidate in tokenizer.batch_decode(beams, skip_special_tokens=True):
                candidate = candidate.strip()
                if useful_model_candidate(source, candidate) and candidate.casefold() not in {c.casefold() for c in candidates}:
                    candidates.append(candidate)
            candidates = rank_by_glossary(candidates, required)
            translated += bool(candidates)
            if not candidates:
                warning = "Model output did not pass structure filters"
            elif required:
                missing = [term.ru for term in required if not matched_term(candidates[0], term)]
                if missing:
                    warning = "Approved terms absent from first suggestion: " + ", ".join(missing)
        else:
            warning = "Skipped: placeholder, markup or fragment"
        candidates = (candidates + [""] * 3)[:3]
        output_rows.append({"key": row["key"], "source": source, "original_kk": row["target"],
                            "kazrush_1": candidates[0], "kazrush_2": candidates[1],
                            "kazrush_3": candidates[2],
                            "approved_glossary_terms": ", ".join(term.ru for term in required),
                            "warning": warning})
        if index % 20 == 0:
            print(f"{index}/{len(rows)}", flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(output_rows)
    return len(rows), translated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corrections", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--glossary", type=Path, help="Use only human-approved terms in this CSV")
    args = parser.parse_args()
    rows, translated = generate(args.corrections, args.model_dir, args.out, args.limit, args.glossary)
    print(f"Saved {rows} rows with {translated} model suggestions to {args.out}")


if __name__ == "__main__":
    main()
