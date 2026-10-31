import json
import tempfile
import unittest
from pathlib import Path

from build_game_glossary import build


class GameGlossaryTests(unittest.TestCase):
    def test_extracts_occurring_terms_without_confusing_game_and_play(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            texts = {
                "ru": {"a": "Игра", "b": "Играть", "c": "Ежедневные задания", "d": "Ежедневные призы"},
                "kk": {"a": "Ойын", "b": "Ойнау", "c": "Күнделікті тапсырмалар", "d": "Күнделікті жүлделер"},
                "en": {"a": "Game", "b": "Play", "c": "Daily tasks", "d": "Daily prizes"},
            }
            for lang, data in texts.items():
                (root / f"{lang}.arb").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            rows = build(root / "ru.arb", root / "kk.arb", root / "en.arb", root / "terms.csv")
            by_term = {row["ru"]: row for row in rows}
            self.assertEqual("1", by_term["игра"]["occurrences"])
            self.assertEqual("1", by_term["играть"]["occurrences"])
            self.assertEqual("1", by_term["ежедневное задание"]["occurrences"])
            self.assertEqual("false", by_term["играть"]["reviewed_by_human"])
            self.assertEqual("", by_term["играть"]["approved_kk"])


if __name__ == "__main__":
    unittest.main()
