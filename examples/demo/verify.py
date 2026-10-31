"""Verify the documented synthetic demo output, without private case data."""

import json
from pathlib import Path


EXPECTED = {
    ("demoGreeting", "placeholder_mismatch"),
    ("demoWelcome", "same_as_source"),
    ("demoMissing", "untranslated"),
    ("demoCount", "plural_mismatch"),
    ("demoGift", "suffix_harmony"),
    ("demoMenuButton", "length_overflow"),
    ("demoNews", "wrong_language"),
    ("demoConfirm", "orthography"),
    ("demoAwkward", "machine_translation_suspect"),
    ("demoToken", "glossary_violation"),
    ("demoExitThree", "inconsistent_term"),
}


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    findings = json.loads((root / "reports/demo.json").read_text(encoding="utf-8"))
    actual = {(row["key"], row["issue_type"]) for row in findings}
    if actual != EXPECTED or len(findings) != len(EXPECTED):
        raise SystemExit(f"Demo differs: missing={EXPECTED - actual}, extra={actual - EXPECTED}")
    if any(row["reviewed_by_human"] for row in findings):
        raise SystemExit("Synthetic demo must not claim human approval")
    print("Public demo verified: 11 documented findings, no human approval claimed.")


if __name__ == "__main__":
    main()
