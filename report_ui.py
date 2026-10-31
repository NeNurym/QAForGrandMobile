"""Readable, offline HTML report for localization findings."""

from __future__ import annotations

import json
from html import escape
from collections import defaultdict
from pathlib import Path


ISSUES = {
    "untranslated": ("Нет перевода", "technical", "Добавьте перевод или подтвердите, что пустая строка нужна по смыслу."),
    "placeholder_mismatch": ("Повреждена переменная", "technical", "Сверьте слова в фигурных скобках: в обоих языках они должны совпадать."),
    "plural_mismatch": ("Повреждена форма числа", "technical", "Сверьте варианты числа в исходном тексте и переводе."),
    "suffix_harmony": ("Окончание после переменной", "technical", "Проверьте окончание после фигурных скобок; оно может быть неправильным для разных значений."),
    "wrong_language": ("Возможно, другой язык", "language", "Проверьте, что фраза написана на нужном языке перевода."),
    "same_as_source": ("Остался русский текст", "language", "Переведите строку, если это не бренд, имя или принятое игровое слово."),
    "machine_translation_suspect": ("Неестественная фраза", "language", "Попросите носителя языка проверить смысл и естественность фразы."),
    "orthography": ("Смешаны алфавиты", "language", "Проверьте похожие латинские и кириллические буквы в слове."),
    "glossary_violation": ("Игровой термин", "terms", "Сверьте слово с игровым глоссарием и контекстом экрана."),
    "inconsistent_term": ("Разные варианты одного слова", "terms", "Сравните повторяющийся текст на других экранах и выберите единый вариант."),
    "length_overflow": ("Текст может не поместиться", "interface", "Проверьте кнопку или заголовок в интерфейсе; при необходимости сократите."),
}
SEVERITY = {"high": ("Срочно", 0), "medium": ("Проверить", 1), "low": ("Сомнение", 2)}
CATEGORIES = {
    "technical": ("Технические", "Пустой перевод, переменные и формы числа"),
    "language": ("Язык и смысл", "Другой язык, русский текст и неестественные фразы"),
    "terms": ("Игровые слова", "Термины и разные варианты одного слова"),
    "interface": ("Интерфейс", "Слишком длинные подписи"),
}
PRIORITY = {kind: i for i, kind in enumerate(ISSUES)}


def group_findings(findings: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for finding in findings:
        groups[str(finding["key"])].append(finding)
    cards = []
    for key, issues in groups.items():
        issues.sort(key=lambda finding: (SEVERITY.get(finding["severity"], ("", 2))[1],
                                         PRIORITY.get(finding["issue_type"], 99)))
        top = issues[0]
        cards.append({"key": key, "issues": issues, "severity": top["severity"],
                      "source": top.get("source", ""), "target": top.get("target", ""),
                      "categories": {ISSUES.get(issue["issue_type"], ("", "language", ""))[1] for issue in issues},
                      "reviewed": all(bool(issue.get("reviewed_by_human")) for issue in issues),
                      "priority": min(PRIORITY.get(issue["issue_type"], 99) for issue in issues)})
    cards.sort(key=lambda card: (SEVERITY.get(card["severity"], ("", 2))[1], card["priority"], card["key"]))
    return cards


def report_rows(findings: list[dict], source=None, target=None, baseline=None, proposals=None, reviewed_keys=None) -> list[dict]:
    """Preserve every entry; no signal does not imply human approval."""
    grouped = {card["key"]: card for card in group_findings(findings)}
    source = source if source is not None else {key: card["source"] for key, card in grouped.items()}
    target = target if target is not None else {key: card["target"] for key, card in grouped.items()}
    baseline = baseline if baseline is not None else target
    proposals = proposals or {}
    keys = {key for data in (source, target, baseline) for key, value in data.items()
            if not str(key).startswith("@") and isinstance(value, str)} | set(grouped)
    rows = []
    for key in sorted(keys):
        card = grouped.get(key, {})
        issues = card.get("issues", [])
        current, before = target.get(key, ""), baseline.get(key, "")
        variants = []
        for value in proposals.get(key, []):
            text = value.get("translation", value.get("text", "")) if isinstance(value, dict) else str(value)
            if text and text not in variants:
                variants.append(text)
        reviewed = key in (reviewed_keys or set())
        metadata = target.get("@" + key, {})
        if isinstance(metadata, dict) and "reviewed_by_human=true" in str(metadata.get("description", "")):
            reviewed = True
        changed = current != before
        status = "reviewed" if reviewed else "changed" if changed else "issue" if issues else "clear"
        rows.append({"key": key, "source": source.get(key, ""), "before": before, "target": current,
                     "changed": changed, "status": status, "severity": card.get("severity", "none"),
                     "categories": sorted(card.get("categories", set())), "proposals": variants[:3],
                     "issues": [{"type": issue["issue_type"],
                                 "label": ISSUES.get(issue["issue_type"], (issue["issue_type"],))[0],
                                 "reason": issue.get("evidence", ""),
                                 "suggestion": issue.get("suggestion", "")} for issue in issues]})
    rank = {"high": 0, "medium": 1, "low": 2, "none": 3}
    return sorted(rows, key=lambda row: (rank.get(row["severity"], 3), row["key"]))


def render_report(findings: list[dict], path: Path, source=None, target=None, baseline=None, proposals=None, reviewed_keys=None) -> None:
    rows = report_rows(findings, source, target, baseline, proposals, reviewed_keys)
    data = {"rows": rows, "labels": {kind: values[0] for kind, values in ISSUES.items()},
            "counts": {"all": len(rows), "issue": sum(bool(row["issues"]) for row in rows),
                       "changed": sum(row["changed"] for row in rows),
                       "reviewed": sum(row["status"] == "reviewed" for row in rows),
                       "proposals": sum(bool(row["proposals"]) for row in rows)}}
    serialized = json.dumps(data, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    template = Path(__file__).with_name("report_template.html").read_text(encoding="utf-8")
    template = template.replace("{{REPORT_DATA}}", serialized)
    artifacts = [("all_data.json", "Все данные · JSON"), ("intl_kk_draft.arb", "Черновик · ARB"),
                 ("intl_kk_fixed.arb", "Одобренные правки · ARB"),
                 ("selected_corrections.csv", "Таблица для подтверждения · CSV")]
    links = [f'<a href="{filename}" download>{escape(label)}</a>' for filename, label in artifacts
             if path.with_name(filename).is_file()]
    template = template.replace("{{OUTPUT_LINKS}}", '<div class="workflow">Сохранить: ' + ' · '.join(links) + '</div>' if links else '')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template, encoding="utf-8")
