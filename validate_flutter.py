#!/usr/bin/env python3
"""Smoke-test Grand Mobile ARB files with a locally installed Flutter SDK."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


VALID_RESOURCE = re.compile(r"^[a-z$][a-zA-Z0-9_$]*$")


def normalized_arb_copies(source: Path, target: Path, destination: Path) -> dict[str, str]:
    """Normalize handout key names only in temporary Flutter smoke-test copies."""
    source_data = json.loads(source.read_text(encoding="utf-8"))
    target_data = json.loads(target.read_text(encoding="utf-8"))
    resource_keys = {key for data in (source_data, target_data) for key in data if not key.startswith("@")}
    used = {key for key in resource_keys if VALID_RESOURCE.fullmatch(key)}
    mapping = {}
    for key in sorted(resource_keys):
        if VALID_RESOURCE.fullmatch(key):
            continue
        candidate = re.sub(r"[^a-zA-Z0-9_$]", "_", key)
        if candidate and candidate[0].isupper():
            candidate = candidate[0].lower() + candidate[1:]
        if not candidate or candidate[0].isdigit() or candidate[0] == "_":
            candidate = "resource" + candidate
        base = candidate
        suffix = 2
        while candidate in used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        mapping[key] = candidate
        used.add(candidate)

    def write_copy(data: dict, name: str) -> None:
        normalized = {}
        for key, value in data.items():
            new_key = key if key.startswith("@@") else "@" + mapping.get(key[1:], key[1:]) if key.startswith("@") else mapping.get(key, key)
            if new_key in normalized:
                raise ValueError(f"Key collision in Flutter validation copy: {new_key}")
            normalized[new_key] = value
        (destination / name).write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")

    write_copy(source_data, "intl_ru.arb")
    write_copy(target_data, "intl_kk.arb")
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(description="Run flutter gen-l10n in a temporary project")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--flutter", default="flutter", help="Flutter executable or full path to flutter.bat")
    parser.add_argument("--normalize-invalid-keys", action="store_true",
                        help="Rename invalid handout keys only in temporary test copies; original ARBs remain unchanged")
    args = parser.parse_args()
    executable = shutil.which(args.flutter)
    if not executable:
        print("Flutter SDK not found. Install Flutter or pass --flutter with its executable path.", file=sys.stderr)
        return 2
    executable = str(Path(executable).resolve())
    for path in (args.source, args.target):
        if not path.is_file():
            print(f"ARB file not found: {path}", file=sys.stderr)
            return 2

    with tempfile.TemporaryDirectory(prefix="locqa_flutter_") as work:
        project = Path(work)
        l10n = project / "lib" / "l10n"
        l10n.mkdir(parents=True)
        if args.normalize_invalid_keys:
            mapping = normalized_arb_copies(args.source, args.target, l10n)
            print(f"Temporary Flutter key mapping: {mapping}")
        else:
            shutil.copyfile(args.source, l10n / "intl_ru.arb")
            shutil.copyfile(args.target, l10n / "intl_kk.arb")
        (project / "pubspec.yaml").write_text(
            "name: locqa_validation\n"
            "description: Temporary ARB validation project\n"
            "environment:\n  sdk: '>=3.0.0 <4.0.0'\n"
            "dependencies:\n  flutter:\n    sdk: flutter\n"
            "flutter:\n  generate: true\n",
            encoding="utf-8",
        )
        (project / "l10n.yaml").write_text(
            "arb-dir: lib/l10n\n"
            "template-arb-file: intl_ru.arb\n"
            "output-localization-file: app_localizations.dart\n"
            "output-dir: lib/generated\n",
            encoding="utf-8",
        )
        run_env = os.environ.copy()
        config_count = int(run_env.get("GIT_CONFIG_COUNT", "0"))
        run_env["GIT_CONFIG_COUNT"] = str(config_count + 1)
        run_env[f"GIT_CONFIG_KEY_{config_count}"] = "safe.directory"
        run_env[f"GIT_CONFIG_VALUE_{config_count}"] = str(Path(executable).parent.parent)
        run_env["FLUTTER_SUPPRESS_ANALYTICS"] = "true"
        run_env["DART_SUPPRESS_ANALYTICS"] = "true"
        result = subprocess.run([executable, "gen-l10n"], cwd=project, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, env=run_env)
        print(result.stdout)
        if result.returncode:
            print(f"flutter gen-l10n failed with code {result.returncode}", file=sys.stderr)
            return result.returncode
        generated = list((project / "lib" / "generated").glob("*.dart"))
        if not generated:
            print("Flutter returned success but generated no Dart localization files.", file=sys.stderr)
            return 1
        print(f"Flutter generated {len(generated)} Dart localization files successfully.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
