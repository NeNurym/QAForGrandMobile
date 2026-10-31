"""Load matching, structurally checked translation drafts; never grant approval."""

from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path

from locqa import icu_forms, placeholders

ROOT = Path(__file__).resolve().parent
CACHE_FILES = (
    ROOT / "corrections.csv",
    ROOT / "private/kazrush_candidates.csv",
    ROOT / "private/qwen_glossary_candidates_v3.csv",
    ROOT / "private/model_candidates.csv",
)
TAGS = re.compile(r"<[^>]+>")


def safe_draft(source: str, candidate: str) -> bool:
    """Structural validity does not imply correct meaning or natural Kazakh."""
    return (bool(candidate.strip())
            and placeholders(source) == placeholders(candidate)
            and TAGS.findall(source) == TAGS.findall(candidate)
            and re.findall(r"\d+", source) == re.findall(r"\d+", candidate)
            and icu_forms(source) == icu_forms(candidate))


def load_proposal_details(source: dict, target: dict, cache_files=None) -> dict[str, list[dict]]:
    """Require exact key, Russian source AND original translation before reuse."""
    result: dict[str, list[dict]] = {}
    for path in CACHE_FILES if cache_files is None else cache_files:
        path = Path(path)
        if not path.is_file():
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                key = row.get("key", "")
                text = source.get(key)
                if not isinstance(text, str) or row.get("source") != text:
                    continue
                original = row.get("original_kk", row.get("target"))
                if original is None or original != target.get(key, ""):
                    continue
                fields = [("translation", "Подготовленный черновик")]
                fields += [(f"kazrush_{i}", "ИИ kazRush") for i in range(1, 4)]
                fields += [("qwen_kk", "ИИ Qwen, черновой глоссарий")]
                fields += [(f"option_{i}", "Подготовленный черновик / NLLB") for i in range(1, 4)]
                for field, origin in fields:
                    candidate = row.get(field, "")
                    if not candidate or candidate == original or not safe_draft(text, candidate):
                        continue
                    options = result.setdefault(key, [])
                    if len(options) >= 3 or any(item["text"].casefold() == candidate.casefold() for item in options):
                        continue
                    options.append({"text": candidate, "origin": origin, "cache_file": path.name,
                                    "reviewed_by_human": False})
    return result


def load_proposals(source: dict, target: dict, cache_files=None) -> dict[str, list[str]]:
    return {key: [item["text"] for item in options]
            for key, options in load_proposal_details(source, target, cache_files).items()}


def generate_proposals(source: dict, target: dict, keys, output_dir: Path,
                       limit: int = 12) -> dict[str, list[str]]:
    """Explicit small offline kazRush run for new inputs. Requires local venv/model."""
    from kazrush_proposals import eligible

    interpreter = ROOT / ".venv/Scripts/python.exe"
    model = ROOT / ".local_models/kazRush-ru-kk"
    if not interpreter.is_file() or not model.is_dir():
        raise RuntimeError("Локальная модель kazRush или Python .venv не найдены")
    selected = [key for key in dict.fromkeys(keys)
                if isinstance(source.get(key), str) and eligible(source[key])][:limit]
    if not selected:
        return {}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_path = output_dir / "ai_input.csv"
    output_path = output_dir / "ai_candidates.csv"
    with input_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["key", "source", "target"])
        writer.writeheader()
        writer.writerows({"key": key, "source": source[key], "target": target.get(key, "")}
                         for key in selected)
    subprocess.run([str(interpreter), str(ROOT / "kazrush_proposals.py"),
                    "--corrections", str(input_path), "--model-dir", str(model),
                    "--out", str(output_path)], check=True, cwd=ROOT)
    return load_proposals(source, target, [output_path])
