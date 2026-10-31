#!/usr/bin/env python3
"""Standalone ARB localization QA. Uses only the Python standard library."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile


DECODER = json.JSONDecoder()
SIMPLE_PLACEHOLDER = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z_0-9]*)\}(?!\})")
ICU_HEAD = re.compile(r"\{\s*([A-Za-z_][A-Za-z_0-9]*)\s*,\s*(plural|selectordinal|select)\s*,")
AFFIX = re.compile(r"\{([A-Za-z_][A-Za-z_0-9]*)\}-(ға|ге|қа|ке|ға|ге|дың|дің|тың|тің|ға|ге|мен|пен|бен)\b", re.I)
SHORT_KEY = re.compile(r"button|btn|tab|title|label|menu|action|header|caption", re.I)
CYRILLIC = re.compile(r"[А-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІіЁё]")
MIXED_SCRIPT = re.compile(r"\b(?=\w*[А-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі])(?=\w*[aeopcxAEOPCX])\w+\b")
SOURCE_EXCEPTIONS = {"бонус", "бизнес", "профиль", "промокод", "неон", "нитро", "турбо", "донат", "арена", "инвентарь", "ранг", "банк", "такси", "скин", "кейс", "баланс", "лидерборд"}
RUSSIAN_GRAMMAR = re.compile(r"(?i)(?:\b(?:вы|ты|вам|ваш|для|чтобы|до|от|при|или|будет|можно|нужно|получить|нажмите)\b|\b[а-яё]+(?:ая|ого|ых|ые|ую|ется|ится|ешь|ите|овать|ению|ания)\b)")


@dataclass
class Entry:
    key: str
    value: object
    start: int
    end: int


def read_arb(path: Path) -> tuple[str, list[Entry], dict[str, object]]:
    """Read top-level JSON pairs without losing repeated @@comment entries or byte spans."""
    raw = path.read_text(encoding="utf-8")
    json.loads(raw)  # Enforce strict JSON syntax, including rejection of trailing commas.
    pos = 0

    def skip_space(p: int) -> int:
        while p < len(raw) and raw[p].isspace():
            p += 1
        return p

    pos = skip_space(pos)
    if raw[pos:pos + 1] != "{":
        raise ValueError(f"{path}: ARB root must be an object")
    pos += 1
    entries: list[Entry] = []
    while True:
        pos = skip_space(pos)
        if raw[pos:pos + 1] == "}":
            pos = skip_space(pos + 1)
            if pos != len(raw):
                raise ValueError(f"{path}: trailing content")
            break
        key, pos = DECODER.raw_decode(raw, pos)
        if not isinstance(key, str):
            raise ValueError(f"{path}: non-string key")
        pos = skip_space(pos)
        if raw[pos:pos + 1] != ":":
            raise ValueError(f"{path}: expected colon after {key}")
        pos = skip_space(pos + 1)
        start = pos
        value, pos = DECODER.raw_decode(raw, pos)
        entries.append(Entry(key, value, start, pos))
        pos = skip_space(pos)
        if raw[pos:pos + 1] == ",":
            pos += 1
        elif raw[pos:pos + 1] != "}":
            raise ValueError(f"{path}: expected comma after {key}")
    values = {e.key: e.value for e in entries if not e.key.startswith("@")}
    # ARB files in the handout contain repeated translation keys as well as
    # repeated @@comment markers. JSON consumers use the final occurrence.
    return raw, entries, values


def icu_forms(text: str) -> list[tuple[str, str, set[str]]]:
    forms = []
    for m in ICU_HEAD.finditer(text):
        depth = 1
        i = m.end()
        while i < len(text) and depth:
            depth += (text[i] == "{") - (text[i] == "}")
            i += 1
        body = text[m.end():i - 1] if depth == 0 else text[m.end():]
        categories = set(re.findall(r"(?:^|\})\s*(zero|one|two|few|many|other|=\d+)\s*\{", body))
        forms.append((m.group(1), m.group(2), categories))
    return forms


def placeholders(text: str) -> Counter[str]:
    result = Counter(SIMPLE_PLACEHOLDER.findall(text))
    result.update(m.group(1) for m in ICU_HEAD.finditer(text))
    return result


def load_glossary(path: Path | None) -> list[dict[str, str]]:
    if not path:
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if not row.get("ru") or not row.get("kk"):
            raise ValueError("glossary requires ru and kk columns")
    return rows


def load_suspect_phrases(path: Path | None) -> tuple[str, ...]:
    if path is None:
        return ()
    return tuple(line.strip().casefold() for line in path.read_text(encoding="utf-8-sig").splitlines()
                 if line.strip() and not line.lstrip().startswith("#"))


def read_xlsx_rows(path: Path, sheet_number: int) -> list[dict[str, str]]:
    """Read an Excel review sheet, including shared and inline string storage."""
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall(f"{ns}si"):
                shared.append("".join(node.text or "" for node in item.iter(f"{ns}t")))
        sheet = ET.fromstring(archive.read(f"xl/worksheets/sheet{sheet_number}.xml"))

    def cell_text(cell: ET.Element) -> str:
        kind = cell.get("t")
        if kind == "inlineStr":
            return "".join(node.text or "" for node in cell.iter(f"{ns}t"))
        value = cell.find(f"{ns}v")
        if value is None:
            return ""
        if kind == "s":
            return shared[int(value.text or "0")]
        return value.text or ""

    rows: list[dict[str, str]] = []
    for row in sheet.iter(f"{ns}row"):
        if int(row.get("r", "0")) < 6:
            continue
        cells = {re.match(r"[A-Z]+", cell.get("r", ""))[0]: cell_text(cell)
                 for cell in row.findall(f"{ns}c") if re.match(r"[A-Z]+", cell.get("r", ""))}
        if cells.get("A", "").strip():
            rows.append(cells)
    return rows


def review_flag(cells: dict[str, str], key: str, column: str = "G") -> str:
    review = cells.get(column, "").strip().casefold()
    if review not in {"да", "нет", "true", "false", ""}:
        raise ValueError(f"{key}: column {column} must be Да or Нет")
    return "true" if review in {"да", "true"} else "false"


def read_review_xlsx(path: Path) -> list[dict[str, str]]:
    """Read edited translations from the first sheet of the review workbook."""
    rows = []
    for cells in read_xlsx_rows(path, 1):
        key = cells.get("A", "").strip()
        new_layout = "I" in cells
        translation_column, review_column, comment_column = ("H", "I", "J") if new_layout else ("F", "G", "H")
        rows.append({"key": key, "translation": cells.get(translation_column, ""),
                     "reviewed_by_human": review_flag(cells, key, review_column),
                     "comment": cells.get(comment_column, "")})
    return rows


def apply_glossary_review(glossary_path: Path, review_path: Path, output_path: Path) -> int:
    with glossary_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        glossary = list(reader)
    if not fields:
        raise ValueError("Empty glossary")
    review = {cells["A"].strip().casefold(): cells for cells in read_xlsx_rows(review_path, 2)}
    if len(review) != len(glossary):
        raise ValueError("Glossary review has missing or duplicate terms")
    approved = 0
    for row in glossary:
        key = row["ru"].strip().casefold()
        if key not in review:
            raise ValueError(f"Glossary term missing from review: {row['ru']}")
        cells = review[key]
        final = cells.get("F", "").strip()
        if not final:
            raise ValueError(f"{row['ru']}: preferred Kazakh term is empty")
        row["kk"] = final
        row["kk_stems"] = cells.get("C", "").strip() or final
        row["reviewed_by_human"] = review_flag(cells, row["ru"])
        approved += row["reviewed_by_human"] == "true"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(glossary)
    return approved


def read_corrections(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() == ".xlsx":
        return read_review_xlsx(path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def approved_empty_keys(entries: list[Entry]) -> set[str]:
    approved = set()
    for entry in entries:
        if not entry.key.startswith("@") or entry.key.startswith("@@") or not isinstance(entry.value, dict):
            continue
        description = str(entry.value.get("description", ""))
        marker = re.findall(r"QA: reviewed_by_human=(true|false)\b([^|]*)", description)
        if marker and marker[-1][0] == "true" and "empty_intentional=true" in marker[-1][1]:
            approved.add(entry.key[1:])
    return approved


def human_reviewed_keys(entries: list[Entry]) -> set[str]:
    reviewed = set()
    for entry in entries:
        if not entry.key.startswith("@") or entry.key.startswith("@@") or not isinstance(entry.value, dict):
            continue
        description = str(entry.value.get("description", ""))
        markers = re.findall(r"QA: reviewed_by_human=(true|false)\b", description)
        if markers and markers[-1] == "true":
            reviewed.add(entry.key[1:])
    return reviewed


def check(source: dict[str, object], target: dict[str, object], glossary: list[dict[str, str]], target_locale: str = "kk", sensitive: bool = False, empty_ok: set[str] | None = None, reviewed_keys: set[str] | None = None, suspect_phrases: tuple[str, ...] = ()) -> list[dict]:
    findings: list[dict] = []
    empty_ok = empty_ok or set()
    reviewed_keys = reviewed_keys or set()
    borrowings = {row["ru"].strip().casefold() for row in glossary
                  if row.get("ru", "").strip().casefold() == row.get("kk", "").strip().casefold()}
    variants: dict[str, set[str]] = defaultdict(set)
    for key, src in source.items():
        if key in target and isinstance(src, str) and isinstance(target[key], str):
            variants[src.strip().casefold()].add(target[key].strip().casefold())

    def add(key: str, kind: str, severity: str, evidence: str, suggestion: str = "", confidence: float = 1.0):
        findings.append({
            "key": key, "issue_type": kind, "severity": severity,
            "source": source.get(key, ""), "target": target.get(key, ""),
            "evidence": evidence, "suggestion": suggestion,
            "confidence": confidence, "reviewed_by_human": key in reviewed_keys,
        })

    for key, src in source.items():
        if not isinstance(src, str):
            continue
        if key not in target or not isinstance(target[key], str) or (target[key] == "" and key not in empty_ok):
            add(key, "untranslated", "high", "Ключ отсутствует или перевод пуст.")
            continue
        tgt = target[key]
        assert isinstance(tgt, str)
        sp, tp = placeholders(src), placeholders(tgt)
        if sp != tp:
            add(key, "placeholder_mismatch", "high", f"Плейсхолдеры: ru={dict(sp)}, kk={dict(tp)}.", confidence=1.0)
        sf, tf = icu_forms(src), icu_forms(tgt)
        if sf or tf:
            if sf != tf or any("other" not in categories for _, _, categories in tf):
                add(key, "plural_mismatch", "high", f"ICU-формы: ru={sf}, kk={tf}.", confidence=0.95)
        if src.strip().casefold() == tgt.strip().casefold() and CYRILLIC.search(src):
            normalized = src.strip().casefold()
            strong_signal = (len(src.split()) >= 4 or len(variants[normalized]) > 1
                             or bool(RUSSIAN_GRAMMAR.search(src)))
            short_format = bool(placeholders(src)) and len(SIMPLE_PLACEHOLDER.sub("", src).strip()) < 10
            if (normalized not in SOURCE_EXCEPTIONS and normalized not in borrowings and not short_format and len(normalized) > 3
                    and not re.fullmatch(r"[\W\d_]+", normalized)
                    and (strong_signal or sensitive)):
                add(key, "same_as_source", "medium" if strong_signal else "low",
                    "Целевой текст совпадает с русским; проверьте, является ли это игровым названием или заимствованием.",
                    confidence=0.8 if strong_signal else 0.35)
        affix_matches = AFFIX.findall(tgt) if target_locale == "kk" else []
        if affix_matches:
            add(key, "suffix_harmony", "high", f"После переменного плейсхолдера стоит фиксированный аффикс: {affix_matches}.", "Переформулировать без аффикса или обрабатывать его в коде.", 0.95)
        if SHORT_KEY.search(key) and len(src) <= 35 and len(tgt) >= max(20, int(len(src) * 1.8)):
            add(key, "length_overflow", "medium", f"Длина ru={len(src)}, kk={len(tgt)}; ключ похож на короткий элемент интерфейса.", confidence=0.7)
        plain_target = re.sub(r"<[^>]*>|\{[^{}]*\}", "", tgt)
        target_letters = [c for c in plain_target if c.isalpha()]
        source_cyrillic = sum(bool(CYRILLIC.fullmatch(c)) for c in src)
        if (target_locale == "kk" and len(target_letters) >= 8 and source_cyrillic >= 5
                and sum(c.isascii() for c in target_letters) / len(target_letters) > 0.7
                and sum(bool(CYRILLIC.fullmatch(c)) for c in target_letters) <= 2):
            add(key, "wrong_language", "high", "Казахский перевод почти целиком написан латиницей, хотя исходная строка русская.", confidence=0.9)
        mixed = MIXED_SCRIPT.findall(tgt)
        if mixed:
            add(key, "orthography", "medium", f"В одном кириллическом слове смешаны латинские и кириллические буквы: {mixed}.", confidence=0.95)
        suspect = [fragment for fragment in suspect_phrases if fragment in tgt.casefold()] if target_locale == "kk" else []
        if suspect:
            add(key, "machine_translation_suspect", "medium",
                f"В казахском тексте есть неестественные или ошибочные сочетания: {suspect}. Нужна проверка носителем.",
                confidence=0.8)

    for row in glossary if target_locale == "kk" else []:
        if (row.get("enforce") or "true").strip().casefold() == "false":
            continue
        ru = row["ru"].strip()
        kk = row["kk"].strip()
        if not ru or not kk:
            continue
        ru_stem = (row.get("ru_stem") or "").strip()
        ru_pattern = re.compile(r"(?<!\w)" + re.escape(ru_stem or ru) + (r"\w*" if ru_stem else r"(?!\w)"), re.I)
        # Allowed variants are curated by the game team; stems permit case suffixes.
        kk_stems = [s.strip().casefold() for s in (row.get("kk_stems") or kk).split("|") if s.strip()]
        for key, src in source.items():
            if key not in target or not isinstance(src, str) or not isinstance(target[key], str):
                continue
            matches_source = (src.strip().casefold() == ru.casefold() if (row.get("scope") or "").strip() == "full"
                              else bool(ru_pattern.search(src)))
            if matches_source and not any(stem in target[key].casefold() for stem in kk_stems):
                add(key, "glossary_violation", "medium", f"Игровой термин «{ru}»: ожидается «{kk}» или разрешённый вариант; проверьте контекст.", kk, 0.65)

    # A strong length outlier among repeated identical source labels can reveal
    # an accidental paste from another screen. Do not assume the majority wins.
    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key, src in source.items():
        if (key in target and isinstance(src, str) and isinstance(target[key], str)
                and 4 <= len(src) <= 25 and re.fullmatch(r"[А-Яа-яЁё -]+", src)):
            groups[src.casefold().strip()].append((key, target[key]))
    for src, entries in groups.items():
        if len(entries) < 3:
            continue
        counts = Counter(value.casefold().strip() for _, value in entries)
        common, count = counts.most_common(1)[0]
        if count < 2:
            continue
        for key, value in entries:
            if counts[value.casefold().strip()] == 1 and len(value) > max(15, len(common) * 2.2):
                add(key, "inconsistent_term", "low", f"Русский текст «{src}» встречается в {len(entries)} ключах; обычный вариант «{common}», этот заметно длиннее. Контекст нужно проверить.", confidence=0.65)

    findings.sort(key=lambda f: (f["key"], f["issue_type"]))
    return findings


def render_html(findings: list[dict], path: Path) -> None:
    rows = []
    for f in findings:
        cells = [f[k] for k in ("key", "issue_type", "severity", "source", "target", "evidence", "suggestion", "confidence", "reviewed_by_human")]
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in cells) + "</tr>")
    doc = """<!doctype html><html lang="ru"><meta charset="utf-8"><title>Loc QA</title>
<style>body{font:14px system-ui;margin:2rem;color:#18212b}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccd4dc;padding:.45rem;vertical-align:top;white-space:pre-wrap}th{background:#e9f0f6;position:sticky;top:0}tr:nth-child(even){background:#f8fafc}input{padding:.5rem;width:20rem}</style>
<h1>Отчёт Loc QA</h1><p>Находок: COUNT. Автоматические находки требуют проверки человеком.</p>
<label>Фильтр <input id="q" oninput="for(const r of document.querySelectorAll('tbody tr'))r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase())"></label>
<table><thead><tr><th>Ключ</th><th>Тип</th><th>Важность</th><th>Русский</th><th>Казахский</th><th>Основание</th><th>Предложение</th><th>Уверенность</th><th>Проверено человеком</th></tr></thead><tbody>ROWS</tbody></table></html>"""
    path.write_text(doc.replace("COUNT", str(len(findings))).replace("ROWS", "\n".join(rows)), encoding="utf-8")


def apply_corrections(input_path: Path, corrections_path: Path, output_path: Path, source_path: Path | None = None, only_reviewed: bool = False) -> tuple[int, int]:
    raw, entries, values = read_arb(input_path)
    by_key = {e.key: e for e in entries}
    source_values = read_arb(source_path)[2] if source_path else {}
    rows = read_corrections(corrections_path)
    changes: list[tuple[int, int, str]] = []
    new_pairs: list[str] = []
    changed = reviewed = 0
    seen = set()

    def add_metadata(key: str, marker: str) -> None:
        meta_key = "@" + key
        if meta_key in by_key:
            meta = by_key[meta_key]
            if not isinstance(meta.value, dict):
                raise ValueError(f"{meta_key}: metadata must be an object")
            data = dict(meta.value)
            original = str(data.get("description", ""))
            data["description"] = (original + " | " + marker).strip(" |")
            changes.append((meta.start, meta.end, json.dumps(data, ensure_ascii=False)))
        else:
            e = by_key[key]
            insertion = ',\n  ' + json.dumps(meta_key, ensure_ascii=False) + ': {"description": ' + json.dumps(marker, ensure_ascii=False) + '}'
            changes.append((e.end, e.end, insertion))

    for row in rows:
        key = row.get("key", "").strip()
        if not key or key in seen or (key not in values and key not in source_values):
            raise ValueError(f"Unknown or duplicate correction key: {key}")
        seen.add(key)
        translation = row.get("translation") or ""
        review_flag = (row.get("reviewed_by_human") or "").strip().lower()
        if review_flag not in {"true", "false"}:
            raise ValueError(f"{key}: reviewed_by_human must be true or false")
        if only_reviewed and review_flag != "true":
            continue
        if review_flag == "true" and isinstance(source_values.get(key), str) and translation:
            source_text = source_values[key]
            if placeholders(source_text) != placeholders(translation):
                raise ValueError(f"{key}: reviewed translation changes placeholders")
            if icu_forms(source_text) != icu_forms(translation):
                raise ValueError(f"{key}: reviewed translation changes ICU forms")
        if not translation:
            if review_flag == "true":
                reason = (row.get("comment") or "").strip().replace("\n", " ")
                if key not in values or values[key] != "" or not reason:
                    raise ValueError(f"{key}: intentional empty requires an existing empty key and a reason in comment")
                add_metadata(key, "QA: reviewed_by_human=true; empty_intentional=true; reason=" + reason)
            continue
        if translation == values.get(key):
            continue
        changed += 1
        reviewed += review_flag == "true"
        meta_key = "@" + key
        marker = "QA: reviewed_by_human=" + review_flag
        if key not in values:
            new_pairs.append("  " + json.dumps(key, ensure_ascii=False) + ": " + json.dumps(translation, ensure_ascii=False))
            new_pairs.append("  " + json.dumps(meta_key, ensure_ascii=False) + ': {"description": ' + json.dumps(marker, ensure_ascii=False) + "}")
            continue
        e = by_key[key]
        changes.append((e.start, e.end, json.dumps(translation, ensure_ascii=False)))
        add_metadata(key, marker)
    if new_pairs:
        closing = raw.rfind("}")
        prefix = ",\n" if entries else "\n"
        changes.append((closing, closing, prefix + ",\n".join(new_pairs) + "\n"))
    for start, end, replacement in sorted(changes, key=lambda x: x[0], reverse=True):
        raw = raw[:start] + replacement + raw[end:]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(raw, encoding="utf-8", newline="\n")
    read_arb(output_path)
    return changed, reviewed


def audit(source_path: Path, baseline_path: Path, target_path: Path) -> dict:
    """Check submission blockers without treating automated suggestions as human work."""
    _, _, source = read_arb(source_path)
    _, _, baseline = read_arb(baseline_path)
    _, entries, target = read_arb(target_path)
    locale = next((e.value for e in entries if e.key == "@@locale"), "kk")
    empty_ok = approved_empty_keys(entries)
    issues = check(source, target, [], str(locale), empty_ok=empty_ok)
    counts = Counter(f["issue_type"] for f in issues)
    meta = {e.key: e.value for e in entries if e.key.startswith("@") and not e.key.startswith("@@")}
    changed = [key for key, value in target.items() if key not in baseline or value != baseline[key]]
    reviewed = unreviewed = unmarked = 0
    for key in changed:
        description = meta.get("@" + key, {})
        description = description.get("description", "") if isinstance(description, dict) else ""
        markers = re.findall(r"QA: reviewed_by_human=(true|false)\b", str(description))
        if not markers:
            unmarked += 1
        elif markers[-1] == "true":
            reviewed += 1
        else:
            unreviewed += 1
    blockers = {
        "untranslated": counts["untranslated"],
        "placeholder_mismatch": counts["placeholder_mismatch"],
        "plural_mismatch": counts["plural_mismatch"],
        "changed_without_review_marker": unmarked,
        "changed_not_human_reviewed": unreviewed,
    }
    return {
        "source_keys": len(source), "target_keys": len(target),
        "changed_keys": len(changed), "human_reviewed_changes": reviewed,
        "approved_intentional_empty": len(empty_ok),
        "flutter_on_path": bool(shutil.which("flutter")),
        "blockers": blockers, "ready_for_flutter_test": not any(blockers.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="locqa", description="ARB localization QA")
    commands = parser.add_subparsers(dest="command", required=True)
    check_cmd = commands.add_parser("check", help="Create JSON and HTML reports")
    for flag in ("source", "target", "out"):
        check_cmd.add_argument("--" + flag, required=True, type=Path)
    check_cmd.add_argument("--glossary", type=Path)
    check_cmd.add_argument("--suspect-phrases", type=Path, help="Private UTF-8 text file with one suspicious phrase per line")
    check_cmd.add_argument("--html", type=Path)
    check_cmd.add_argument("--sensitive", action="store_true", help="Include low-confidence exact Russian matches")
    fix_cmd = commands.add_parser("apply", help="Apply reviewed translations without reformatting ARB")
    for flag in ("target", "corrections", "out"):
        fix_cmd.add_argument("--" + flag, required=True, type=Path)
    fix_cmd.add_argument("--source", type=Path, help="Required when adding previously missing keys")
    fix_cmd.add_argument("--only-reviewed", action="store_true", help="Apply only human-approved rows")
    audit_cmd = commands.add_parser("audit", help="Check structural and human-review completion")
    for flag in ("source", "baseline", "target", "out"):
        audit_cmd.add_argument("--" + flag, required=True, type=Path)
    glossary_cmd = commands.add_parser("glossary-apply", help="Save reviewed terms from the second Excel sheet")
    for flag in ("glossary", "review", "out"):
        glossary_cmd.add_argument("--" + flag, required=True, type=Path)
    args = parser.parse_args()
    if args.command == "check":
        _, _, source = read_arb(args.source)
        _, target_entries, target = read_arb(args.target)
        locale = next((e.value for e in target_entries if e.key == "@@locale"), None)
        if not isinstance(locale, str):
            locale = args.target.stem.rsplit("_", 1)[-1]
        findings = check(source, target, load_glossary(args.glossary), locale, args.sensitive,
                         approved_empty_keys(target_entries), human_reviewed_keys(target_entries),
                         load_suspect_phrases(args.suspect_phrases))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(findings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        html_path = args.html or args.out.with_suffix(".html")
        render_html(findings, html_path)
        counts = Counter(f["issue_type"] for f in findings)
        print(f"{len(findings)} findings: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        print(f"Reports: {args.out}, {html_path}")
    elif args.command == "apply":
        changed, reviewed = apply_corrections(args.target, args.corrections, args.out, args.source, args.only_reviewed)
        print(f"Applied {changed} corrections ({reviewed} marked human-reviewed): {args.out}")
    elif args.command == "audit":
        result = audit(args.source, args.baseline, args.target)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["ready_for_flutter_test"]:
            sys.exit(1)
    else:
        approved = apply_glossary_review(args.glossary, args.review, args.out)
        print(f"Glossary saved: {len(load_glossary(args.out))} terms ({approved} human-reviewed): {args.out}")


if __name__ == "__main__":
    main()
