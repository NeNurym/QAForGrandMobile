#!/usr/bin/env python3
"""Merge the three independent human review workbooks into one corrections CSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from locqa import read_review_xlsx


FIELDS = ["key", "translation", "reviewed_by_human", "comment", "reviewer"]


def merge_reviews(parts: list[Path], full: Path, output: Path) -> tuple[int, int]:
    expected = [row["key"] for row in read_review_xlsx(full)]
    if len(expected) != len(set(expected)):
        raise ValueError("Full workbook contains duplicate keys")
    merged: dict[str, dict[str, str]] = {}
    for index, part in enumerate(parts, 1):
        for row in read_review_xlsx(part):
            key = row["key"]
            if key in merged:
                raise ValueError(f"Duplicate review key: {key}")
            if key not in expected:
                raise ValueError(f"Unexpected review key: {key}")
            if row["reviewed_by_human"] == "true" and not row["translation"] and not row["comment"].strip():
                raise ValueError(f"{key}: approved empty translation needs a reason in column J")
            merged[key] = {**row, "reviewer": f"Проверяющий {index}"}
    missing = set(expected) - set(merged)
    if missing:
        raise ValueError(f"Missing {len(missing)} keys, for example: {sorted(missing)[0]}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(merged[key] for key in expected)
    return len(expected), sum(row["reviewed_by_human"] == "true" for row in merged.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", type=Path, required=True, help="Original unsplit workbook for key coverage")
    parser.add_argument("--parts", type=Path, nargs="+", required=True, help="Edited reviewer workbooks")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    count, reviewed = merge_reviews(args.parts, args.full, args.out)
    print(f"Merged {count} keys; {reviewed} approved by humans; output: {args.out}")


if __name__ == "__main__":
    main()
