import csv
import tempfile
import unittest
from pathlib import Path

from glossary_runtime import load_approved_terms, rank_by_glossary, required_terms


class GlossaryRuntimeTests(unittest.TestCase):
    def test_unapproved_terms_are_never_used_and_approved_terms_rerank(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "terms.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["ru", "ru_search", "kk_draft", "approved_kk", "reviewed_by_human", "use_for_ranking"])
                writer.writeheader()
                writer.writerow({"ru": "награда", "ru_search": r"наград\w*", "kk_draft": "жүлде",
                                 "approved_kk": "сыйлық", "reviewed_by_human": "true"})
                writer.writerow({"ru": "приз", "ru_search": r"приз\w*", "kk_draft": "жүлде",
                                 "reviewed_by_human": "false"})
                writer.writerow({"ru": "карта", "ru_search": r"карт\w*", "approved_kk": "карта",
                                 "reviewed_by_human": "true", "use_for_ranking": "false"})
            required = required_terms("Награды и призы", load_approved_terms(path))
            self.assertEqual(["награда"], [term.ru for term in required])
            self.assertEqual(["Сыйлықтар мен жүлделер", "Жүлделер"],
                             rank_by_glossary(["Жүлделер", "Сыйлықтар мен жүлделер"], required))

    def test_approved_term_without_kazakh_text_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "terms.csv"
            path.write_text("ru,approved_kk,reviewed_by_human\nнаграда,,true\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "needs Kazakh"):
                load_approved_terms(path)


if __name__ == "__main__":
    unittest.main()
