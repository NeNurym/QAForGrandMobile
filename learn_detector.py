#!/usr/bin/env python3
"""Train a small, honest QA baseline on human-approved localization examples.

This is a learned detector, but it is not a multilingual language model. Its
held-out real-error metrics are reported separately from synthetic metrics.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
from collections import defaultdict
from pathlib import Path

from locqa import placeholders, read_arb, read_corrections


GOLD_FIELDS = ["key", "source", "original_kk", "approved_kk", "suggested_issue_type", "reviewer", "reviewed_by_human", "comment"]
CYR = re.compile(r"[А-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІіЁё]")


def export_gold(source_path: Path, baseline_path: Path, review_path: Path,
                output_path: Path, reviewer: str, issues_path: Path | None = None) -> int:
    source = read_arb(source_path)[2]
    baseline = read_arb(baseline_path)[2]
    rows = read_corrections(review_path)
    issue_by_key = {}
    if issues_path:
        with issues_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                issue_by_key[row["key"]] = row.get("issue_type", "")
    gold = []
    for row in rows:
        if row["reviewed_by_human"] != "true":
            continue
        key = row["key"]
        if key not in source or key not in baseline:
            raise ValueError(f"Reviewed key missing from ARB: {key}")
        approved = row["translation"]
        comment = row.get("comment", "").strip()
        if not approved and not (baseline[key] == "" and comment):
            raise ValueError(f"{key}: reviewed row needs a final translation or a reason for intentional empty")
        if placeholders(str(source[key])) != placeholders(approved):
            raise ValueError(f"{key}: approved translation changes placeholders")
        gold.append({"key": key, "source": source[key], "original_kk": baseline[key],
                     "approved_kk": approved, "suggested_issue_type": issue_by_key.get(key, ""),
                     "reviewer": row.get("reviewer") or reviewer,
                     "reviewed_by_human": "true", "comment": comment})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=GOLD_FIELDS)
        writer.writeheader()
        writer.writerows(gold)
    return len(gold)


def load_gold(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not all(set(GOLD_FIELDS).issubset(row) for row in rows):
        raise ValueError("Gold CSV must contain " + ", ".join(GOLD_FIELDS))
    if len({row["key"] for row in rows}) != len(rows):
        raise ValueError("Gold CSV contains duplicate keys")
    if any(row["reviewed_by_human"].strip().casefold() != "true" or not row["reviewer"].strip() for row in rows):
        raise ValueError("Every gold row needs a human review flag and reviewer")
    for row in rows:
        if placeholders(row["source"]) != placeholders(row["approved_kk"]):
            raise ValueError(f"{row['key']}: gold translation changes placeholders")
        if not row["approved_kk"] and not row["comment"].strip():
            raise ValueError(f"{row['key']}: intentional empty gold needs a comment")
    return rows


def split_gold(rows: list[dict[str, str]], holdout: float = 0.25) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Split source families, so similar synthetic siblings cannot leak."""
    groups = defaultdict(list)
    for row in rows:
        norm = re.sub(r"\s+", " ", row["source"].casefold()).strip()
        groups[norm].append(row)
    train, test = [], []
    for source_text, group in groups.items():
        score = int(hashlib.sha256(source_text.encode("utf-8")).hexdigest()[:12], 16) / 16**12
        (test if score < holdout else train).extend(group)
    return train, test


def corrupt(row: dict[str, str], pool: list[dict[str, str]]) -> list[tuple[str, str]]:
    approved = row["approved_kk"]
    source = row["source"]
    candidates = []
    if source.casefold().strip() != approved.casefold().strip() and CYR.search(source):
        candidates.append((source, "copied_source"))
    names = list(placeholders(approved))
    if names:
        token = "{" + names[0] + "}"
        candidates.append((approved.replace(token, "", 1), "placeholder_removed"))
    words = approved.split()
    if len(words) >= 4:
        candidates.append((" ".join(words[: len(words) // 2]), "meaning_omitted"))
    alternatives = [other for other in pool if other["key"] != row["key"]
                    and other["approved_kk"] and other["source"] != source]
    if alternatives:
        index = int(hashlib.sha256(row["key"].encode("utf-8")).hexdigest()[:8], 16) % len(alternatives)
        candidates.append((alternatives[index]["approved_kk"], "wrong_meaning"))
    return [(text, kind) for text, kind in candidates if text and text != approved]


def examples(rows: list[dict[str, str]], synthetic: bool) -> list[tuple[str, str, int, str, str]]:
    output = []
    for row in rows:
        output.append((row["source"], row["approved_kk"], 0, "approved", row["key"]))
        if row["original_kk"] != row["approved_kk"]:
            output.append((row["source"], row["original_kk"], 1, "real", row["key"]))
        if synthetic:
            output.extend((row["source"], text, 1, kind, row["key"])
                          for text, kind in corrupt(row, rows))
    return output


def features(source: str, target: str) -> dict[str, float]:
    src = source.casefold().strip()
    tgt = target.casefold().strip()
    result = {
        "bias": 1.0,
        "empty": float(not tgt),
        "same_source": float(bool(src) and src == tgt),
        "placeholder_diff": float(placeholders(source) != placeholders(target)),
        "length_ratio": min(len(target) / max(1, len(source)), 4) / 4,
        "cyr_ratio": sum(bool(CYR.fullmatch(c)) for c in target) / max(1, len(target)),
    }
    # Sparse lexical signals learn recurring errors but cannot replace a
    # pretrained multilingual semantic model.
    for prefix, value in (("s", src), ("t", tgt)):
        compact = re.sub(r"\s+", " ", value)[:250]
        grams = {compact[i:i + 3] for i in range(max(0, len(compact) - 2))}
        for gram in grams:
            digest = hashlib.blake2b((prefix + gram).encode("utf-8"), digest_size=2).hexdigest()
            result[f"{prefix}{digest}"] = 1.0
    return result


def sigmoid(value: float) -> float:
    value = max(-30.0, min(30.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def predict(weights: dict[str, float], source: str, target: str) -> float:
    return sigmoid(sum(weights.get(name, 0.0) * value for name, value in features(source, target).items()))


def fit(train_rows: list[dict[str, str]], epochs: int = 20) -> dict[str, float]:
    samples = examples(train_rows, synthetic=True)
    weights: dict[str, float] = {}
    rng = random.Random(17)
    for epoch in range(epochs):
        rng.shuffle(samples)
        rate = 0.18 / (1 + epoch * 0.13)
        for source, target, label, _, _ in samples:
            vector = features(source, target)
            error = label - sigmoid(sum(weights.get(k, 0.0) * v for k, v in vector.items()))
            for name, value in vector.items():
                weights[name] = weights.get(name, 0.0) + rate * (error * value - 0.0002 * weights.get(name, 0.0))
    return weights


def score(weights: dict[str, float], samples: list[tuple[str, str, int, str, str]], threshold: float = 0.5) -> dict:
    tp = fp = fn = tn = 0
    by_kind = defaultdict(lambda: {"total": 0, "found": 0})
    for source, target, label, kind, _ in samples:
        detected = predict(weights, source, target) >= threshold
        if label:
            by_kind[kind]["total"] += 1
            by_kind[kind]["found"] += detected
        tp += bool(label and detected)
        fp += bool(not label and detected)
        fn += bool(label and not detected)
        tn += bool(not label and not detected)
    return {"examples": len(samples), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "by_kind": dict(by_kind)}


def train(gold_path: Path, model_path: Path, metrics_path: Path) -> dict:
    rows = load_gold(gold_path)
    if len(rows) < 20:
        raise ValueError("Need at least 20 distinct human-approved keys; current count: " + str(len(rows)))
    train_rows, test_rows = split_gold(rows)
    if len(train_rows) < 10 or len(test_rows) < 3:
        raise ValueError("Not enough source families in both train and held-out sets")
    weights = fit(train_rows)
    real_test = examples(test_rows, synthetic=False)
    synthetic_test = examples(test_rows, synthetic=True)
    synthetic_test = [item for item in synthetic_test if item[3] != "real"]
    metrics = {"human_approved_keys": len(rows), "train_keys": len(train_rows),
               "held_out_keys": len(test_rows),
               "held_out_real": score(weights, real_test),
               "held_out_synthetic": score(weights, synthetic_test),
               "note": "Real and synthetic metrics are separate. This lexical baseline does not establish semantic understanding."}
    model_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(json.dumps({"version": 1, "weights": weights, "train_keys": [r["key"] for r in train_rows]}, ensure_ascii=False), encoding="utf-8")
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return metrics


def scan(model_path: Path, source_path: Path, target_path: Path, output_path: Path) -> int:
    model = json.loads(model_path.read_text(encoding="utf-8"))
    source = read_arb(source_path)[2]
    target = read_arb(target_path)[2]
    results = []
    for key, src in source.items():
        if not isinstance(src, str):
            continue
        tgt = target.get(key, "")
        if not isinstance(tgt, str):
            continue
        model_score = predict(model["weights"], src, tgt)
        results.append({"key": key, "source": src, "target": tgt,
                        "model_score": round(model_score, 4),
                        "status": "error" if model_score >= 0.7 else "uncertain" if model_score >= 0.35 else "no_issue",
                        "reviewed_by_human": False})
    results.sort(key=lambda row: row["model_score"], reverse=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(results)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export-gold")
    for name in ("source", "baseline", "review", "out"):
        export.add_argument("--" + name, type=Path, required=True)
    export.add_argument("--reviewer", required=True)
    export.add_argument("--issues", type=Path, help="Optional review queue CSV with issue types")
    training = commands.add_parser("train")
    for name in ("gold", "model", "metrics"):
        training.add_argument("--" + name, type=Path, required=True)
    scanning = commands.add_parser("scan")
    for name in ("model", "source", "target", "out"):
        scanning.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.command == "export-gold":
        print(f"Exported {export_gold(args.source, args.baseline, args.review, args.out, args.reviewer, args.issues)} human-approved keys to {args.out}")
    elif args.command == "train":
        print(json.dumps(train(args.gold, args.model, args.metrics), ensure_ascii=False, indent=2))
    else:
        print(f"Scanned {scan(args.model, args.source, args.target, args.out)} keys to {args.out}")


if __name__ == "__main__":
    main()
