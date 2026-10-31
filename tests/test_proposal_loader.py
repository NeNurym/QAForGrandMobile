import csv
import tempfile
import unittest
from pathlib import Path

from proposal_loader import load_proposals, load_proposal_details, safe_draft


class ProposalLoaderTests(unittest.TestCase):
    def test_cached_translation_requires_exact_input_and_safe_structure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["key", "source", "original_kk", "kazrush_1"])
                writer.writeheader()
                writer.writerows([
                    {"key": "ok", "source": "Привет {name}", "original_kk": "bad", "kazrush_1": "Сәлем {name}"},
                    {"key": "changed", "source": "Старое", "original_kk": "bad", "kazrush_1": "Сәлем"},
                    {"key": "reviewed", "source": "Привет", "original_kk": "old", "kazrush_1": "Сәлем"},
                    {"key": "unsafe", "source": "Привет {name}", "original_kk": "bad", "kazrush_1": "Сәлем"},
                ])
            source = {"ok": "Привет {name}", "changed": "Новое", "reviewed": "Привет", "unsafe": "Привет {name}"}
            target = {"ok": "bad", "changed": "bad", "reviewed": "new", "unsafe": "bad"}
            self.assertEqual({"ok": ["Сәлем {name}"]}, load_proposals(source, target, [path]))
            self.assertFalse(load_proposal_details(source, target, [path])["ok"][0]["reviewed_by_human"])

    def test_numbers_and_tags_cannot_change(self):
        self.assertFalse(safe_draft("<g>10</g>", "<g>20</g>"))
        self.assertFalse(safe_draft("<g>10</g>", "10"))


if __name__ == "__main__":
    unittest.main()
