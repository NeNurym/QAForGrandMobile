import csv
import json
import tempfile
import unittest
from pathlib import Path

from learn_detector import GOLD_FIELDS, corrupt, export_gold, load_gold, split_gold, train
from zipfile import ZipFile


class LearningTests(unittest.TestCase):
    def test_train_uses_source_family_holdout_and_reports_real_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = []
            for index in range(80):
                rows.append({"key": f"key_{index}", "source": f"Русская строка номер {index}",
                             "original_kk": f"Нашар аударма {index}", "approved_kk": f"Дұрыс аударма {index}",
                             "suggested_issue_type": "wrong_translation", "reviewer": "A", "reviewed_by_human": "true", "comment": ""})
            rows.append(dict(rows[0], key="duplicate_source", original_kk="Басқа қате"))
            train_rows, test_rows = split_gold(rows)
            self.assertFalse({r["source"] for r in train_rows} & {r["source"] for r in test_rows})
            gold = root / "gold.csv"
            with gold.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=GOLD_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            metrics = train(gold, root / "model.json", root / "metrics.json")
            self.assertEqual(81, metrics["human_approved_keys"])
            self.assertEqual(metrics["held_out_keys"] * 2, metrics["held_out_real"]["examples"])
            self.assertTrue((root / "model.json").is_file())
            self.assertTrue(json.loads((root / "metrics.json").read_text("utf-8"))["held_out_synthetic"])

    def test_refuses_unreviewed_gold(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gold.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=GOLD_FIELDS)
                writer.writeheader()
                writer.writerow({"key": "a", "source": "Привет", "approved_kk": "Сәлем",
                                 "reviewer": "A", "reviewed_by_human": "false"})
            with self.assertRaisesRegex(ValueError, "human review"):
                load_gold(path)

    def test_corruptions_are_labeled_and_do_not_modify_gold(self):
        row = {"key": "one", "source": "Привет {name}", "approved_kk": "Сәлем {name}"}
        bad = corrupt(row, [row])
        self.assertIn(("Сәлем ", "placeholder_removed"), bad)
        self.assertEqual("Сәлем {name}", row["approved_kk"])

    def test_export_only_human_approved_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "ru.arb"
            baseline = root / "kk.arb"
            review = root / "review.xlsx"
            source.write_text('{"a":"Привет","b":"Пока"}', encoding="utf-8")
            baseline.write_text('{"a":"Привет","b":"Сау бол"}', encoding="utf-8")
            ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
            sheet = f'''<worksheet xmlns="{ns}"><sheetData>
            <row r="6"><c r="A6" t="inlineStr"><is><t>a</t></is></c><c r="H6" t="inlineStr"><is><t>Сәлем</t></is></c><c r="I6" t="inlineStr"><is><t>Да</t></is></c></row>
            <row r="7"><c r="A7" t="inlineStr"><is><t>b</t></is></c><c r="H7" t="inlineStr"><is><t>Сау бол</t></is></c><c r="I7" t="inlineStr"><is><t>Нет</t></is></c></row>
            </sheetData></worksheet>'''
            with ZipFile(review, "w") as archive:
                archive.writestr("xl/worksheets/sheet1.xml", sheet)
            gold = root / "gold.csv"
            self.assertEqual(1, export_gold(source, baseline, review, gold, "Носитель"))
            self.assertEqual(["a"], [r["key"] for r in load_gold(gold)])


if __name__ == "__main__":
    unittest.main()
