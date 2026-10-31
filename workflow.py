#!/usr/bin/env python3
"""Folder-based localization workflow: input -> result, without changing originals."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from locqa import (apply_corrections, approved_empty_keys, audit, check,
                   human_reviewed_keys, load_glossary, read_arb)
from report_ui import render_report

ROOT = Path(__file__).resolve().parent


def find_inputs(folder: Path) -> tuple[Path, Path]:
    paths = sorted(folder.glob("*.arb"))
    by_locale: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        _, entries, _ = read_arb(path)
        locale = next((e.value for e in entries if e.key == "@@locale"), "")
        if not locale:
            locale = path.stem.rsplit("_", 1)[-1]
        by_locale[str(locale).replace("-", "_").split("_")[0].lower()].append(path)
    for locale in ("ru", "kk"):
        if len(by_locale[locale]) != 1:
            raise ValueError(f"В папке {folder} нужен ровно один ARB языка {locale}. "
                             "Назовите файлы intl_ru.arb и intl_kk.arb либо укажите @@locale внутри.")
    return by_locale["ru"][0], by_locale["kk"][0]


def save_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(input_dir: Path, output_dir: Path, ai_limit: int = 12) -> Path:
    input_dir, output_dir = input_dir.resolve(), output_dir.resolve()
    if input_dir == output_dir or input_dir in output_dir.parents or output_dir in input_dir.parents:
        raise ValueError("Папки input и result должны быть отдельными, не вложенными друг в друга.")
    source_path, target_path = find_inputs(input_dir)
    source = read_arb(source_path)[2]
    baseline = read_arb(target_path)[2]
    output_dir.mkdir(parents=True, exist_ok=True)
    result_arb = output_dir / "intl_kk_fixed.arb"
    draft_arb = output_dir / "intl_kk_draft.arb"
    corrections = input_dir / "corrections.csv"
    correction_rows = []
    if corrections.exists():
        with corrections.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                key = row.get("key", "")
                if key not in source or ("source" in row and row["source"] != source[key]) or ("target" in row and row["target"] != baseline.get(key, "")):
                    print(f"Пропущено устаревшее исправление: {key}")
                    continue
                correction_rows.append(row)
    glossary_path = input_dir / "glossary.csv"
    glossary = load_glossary(glossary_path if glossary_path.exists() else None)
    from proposal_loader import generate_proposals, load_proposals, load_proposal_details, safe_draft
    proposals: dict[str, list[str]] = {}
    origins: dict = {}
    proposals = load_proposals(source, baseline)
    origins = load_proposal_details(source, baseline)
    supplied_proposals = input_dir / "proposals.json"
    if supplied_proposals.exists():
        supplied = json.loads(supplied_proposals.read_text(encoding="utf-8-sig"))
        if not isinstance(supplied, dict):
            raise ValueError("proposals.json должен содержать объект: ключ → список вариантов.")
        for key, values in supplied.items():
            if key not in source or not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise ValueError(f"Некорректные предложения для {key} в proposals.json")
            valid = [value for value in values if safe_draft(source[key], value)][:3]
            if len(valid) != min(3, len(values)):
                print(f"Пропущены структурно неверные предложения: {key}")
            proposals[key] = valid
            origins[key] = [{"text": v, "origin": "input/proposals.json; не проверено"} for v in valid]
    original_issues = check(source, baseline, glossary, "kk")
    pending = list(dict.fromkeys(f["key"] for f in original_issues if not proposals.get(f["key"])))
    if ai_limit > 0 and pending:
        print(f"ИИ переводит до {ai_limit} новых строк. Дождитесь результата…", flush=True)
        try:
            generated = generate_proposals(source, baseline, pending, output_dir, ai_limit)
            proposals.update(generated)
            origins.update(load_proposal_details(source, baseline, [output_dir / "ai_candidates.csv"]))
        except (RuntimeError, OSError, subprocess.SubprocessError) as error:
            print(f"ИИ не запущен: {error}. Проверка правил продолжится.")
    remaining = sum(not proposals.get(key) for key in pending)
    print(f"Сигналы без готового предложения ИИ: {remaining} строк.")
    selected = {}
    for row in correction_rows:
        text = row.get("translation", "")
        if text and not safe_draft(source[row["key"]], text):
            print(f"Пропущено структурно неверное исправление: {row['key']}")
            continue
        selected[row["key"]] = row
    for key, values in proposals.items():
        existing = selected.get(key, {})
        needs_draft = not existing.get("translation") and existing.get("reviewed_by_human", "false").lower() != "true"
        if needs_draft and values and safe_draft(source[key], values[0]):
            selected[key] = {"key": key, "translation": values[0], "reviewed_by_human": "false"}
    selected_path = output_dir / "selected_corrections.csv"
    with selected_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["key", "source", "target", "translation", "reviewed_by_human", "comment"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows({**row, "source": source[key], "target": baseline.get(key, "")} for key, row in selected.items())
    changed, reviewed = apply_corrections(target_path, selected_path, draft_arb, source_path)
    approved_changed, _ = apply_corrections(target_path, selected_path, result_arb, source_path, only_reviewed=True)
    _, entries, result = read_arb(draft_arb)
    reviewed_set = human_reviewed_keys(entries)
    findings = check(source, result, glossary, "kk", empty_ok=approved_empty_keys(entries),
                     reviewed_keys=reviewed_set)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for finding in findings:
        grouped[finding["key"]].append(finding)
    rows = [{"key": key, "source": source.get(key, ""), "current": baseline.get(key, ""),
             "result": result.get(key, ""), "changed": baseline.get(key) != result.get(key),
             "reviewed_by_human": key in reviewed_set,
             "proposals": proposals.get(key, []), "proposal_details": origins.get(key, []),
             "findings": grouped[key]}
            for key in dict.fromkeys([*source, *result])]
    save_json(output_dir / "all_data.json", rows)
    save_json(output_dir / "issues.json", findings)
    save_json(output_dir / "audit.json", audit(source_path, target_path, result_arb))
    save_json(output_dir / "draft_audit.json", audit(source_path, target_path, draft_arb))
    render_report(findings, output_dir / "index.html", source=source, target=result,
                  baseline=baseline, proposals=proposals, reviewed_keys=reviewed_set)
    print(f"Вход: {source_path.name} + {target_path.name}")
    print(f"Всего строк: {len(rows)}. Сигналов после обработки: {len(findings)}.")
    print(f"Изменено: {changed}; подтверждено человеком: {reviewed}.")
    if not corrections.exists():
        print("corrections.csv отсутствует: подтвержденный ARB повторяет входной перевод. "
              "Варианты ИИ собраны отдельно в черновой ARB.")
    elif changed > reviewed:
        print(f"ВНИМАНИЕ: {changed - reviewed} изменений — черновики без одобрения человека.")
    print(f"Предложения доступны для {sum(bool(v) for v in proposals.values())} строк.")
    print(f"Открыть: {output_dir / 'index.html'}")
    print(f"Все данные: {output_dir / 'all_data.json'}")
    print(f"Черновой ARB ({changed} правок): {draft_arb}")
    print(f"Подтвержденный ARB ({approved_changed} правок): {result_arb}")
    return output_dir / "index.html"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "input")
    parser.add_argument("--output", type=Path, default=ROOT / "result")
    parser.add_argument("--ai-limit", type=int, default=12, help="Максимум новых строк для локального ИИ, 0 — только готовые варианты")
    parser.add_argument("--no-open", action="store_true", help="Служебный флаг .cmd: без браузера и паузы")
    args = parser.parse_args()
    try:
        if args.ai_limit < 0:
            raise ValueError("--ai-limit должен быть 0 или больше")
        run(args.input, args.output, args.ai_limit)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(f"ОШИБКА: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
