#!/usr/bin/env python3
"""Generate optional, unverified ru->kk alternatives with a local NLLB model.

The translation model is used only to draft options. It never marks human
approval or writes the final ARB.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from locqa import placeholders


FIELDS = ["key", "source", "original_kk", "issue_type", "option_1", "option_2", "option_3", "model", "warning"]
TAG = re.compile(r"<[^>]+>")


def safe_candidate(source: str, candidate: str) -> bool:
    return (bool(candidate.strip()) and placeholders(source) == placeholders(candidate)
            and TAG.findall(source) == TAG.findall(candidate))


def useful_model_candidate(source: str, candidate: str) -> bool:
    if not safe_candidate(source, candidate) or source.strip().casefold() == candidate.strip().casefold():
        return False
    if source.rstrip().endswith(":") and not candidate.rstrip().endswith(":"):
        return False
    if not source.rstrip().endswith((".", "!", "?", ":", "…")) and candidate.rstrip().endswith((".", "!", "?", "…")):
        return False
    if re.findall(r"\d+", source) != re.findall(r"\d+", candidate):
        return False
    return True


def generate(corrections_path: Path, model_dir: Path, out_path: Path, limit: int | None = None) -> int:
    try:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    except ImportError as error:
        raise RuntimeError("Install torch, transformers<5 and sentencepiece in a local virtual environment") from error

    with corrections_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if limit is not None:
        rows = rows[:limit]
    torch.set_num_threads(min(6, torch.get_num_threads()))
    tokenizer = AutoTokenizer.from_pretrained(model_dir, src_lang="rus_Cyrl", local_files_only=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_dir, local_files_only=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device).eval()
    result = []
    for index, row in enumerate(rows, 1):
        source = row["source"]
        draft = row.get("translation", "")
        options = [draft] if safe_candidate(source, draft) else []
        had_draft = bool(options)
        warning = "" if options or not draft else "existing draft has invalid placeholders or tags"
        # Translating markup or placeholders directly can silently damage ARB.
        # Technical rows already have rule-based drafts and stay human-reviewed.
        suitable_source = (len(source.strip()) >= 15 and len(source.split()) >= 2
                           and not source.strip().isupper() and not source.endswith(" "))
        if not placeholders(source) and not TAG.search(source) and suitable_source:
            inputs = tokenizer(source, return_tensors="pt", truncation=True, max_length=480).to(device)
            with torch.inference_mode():
                outputs = model.generate(
                    **inputs, forced_bos_token_id=tokenizer.convert_tokens_to_ids("kaz_Cyrl"),
                    num_beams=6,
                    num_return_sequences=3, max_new_tokens=min(180, max(20, len(source) // 2 + 15)),
                    early_stopping=True,
                )
            for candidate in tokenizer.batch_decode(outputs, skip_special_tokens=True):
                candidate = candidate.strip()
                if useful_model_candidate(source, candidate) and candidate.casefold() not in {text.casefold() for text in options}:
                    options.append(candidate)
                if len(options) >= 3:
                    break
        else:
            warning = (warning + "; " if warning else "") + "model skipped because of placeholders, markup or short/fragmentary source"
        model_used = len(options) > int(had_draft)
        options = (options + [""] * 3)[:3]
        result.append({"key": row["key"], "source": source, "original_kk": row["target"],
                       "issue_type": row.get("issue_type", ""),
                       "option_1": options[0], "option_2": options[1], "option_3": options[2],
                       "model": "facebook/nllb-200-distilled-600M" if model_used else "",
                       "warning": warning})
        if index % 10 == 0:
            print(f"Prepared {index}/{len(rows)} candidates", flush=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(result)
    return len(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corrections", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    print(f"Saved {generate(args.corrections, args.model_dir, args.out, args.limit)} review rows to {args.out}")


if __name__ == "__main__":
    main()
