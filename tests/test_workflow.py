import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow import find_inputs, run


class WorkflowTests(unittest.TestCase):
    def test_folder_run_preserves_inputs_and_separates_drafts_from_approvals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "input"
            folder.mkdir()
            ru = {"@@locale": "ru", "one": "Привет", "two": "Пока"}
            kk = {"@@locale": "kk", "one": "Сәлем", "two": "", "extra": "Артық"}
            (folder / "intl_ru.arb").write_text(json.dumps(ru), encoding="utf-8")
            target = folder / "intl_kk.arb"
            original = json.dumps(kk)
            target.write_text(original, encoding="utf-8")
            with (folder / "corrections.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["key", "source", "target", "translation", "reviewed_by_human"])
                writer.writeheader()
                writer.writerows([
                    {"key": "one", "source": "Чужой текст", "target": "Сәлем", "translation": "Не использовать", "reviewed_by_human": "true"},
                    {"key": "two", "source": "Пока", "target": "", "translation": "", "reviewed_by_human": "false"},
                ])
            with patch("workflow.render_report"), patch("proposal_loader.load_proposals", return_value={"two": ["Сау бол"]}), patch("proposal_loader.load_proposal_details", return_value={}):
                run(folder, root / "result", ai_limit=0)
            data = json.loads((root / "result/all_data.json").read_text(encoding="utf-8"))
            self.assertEqual(3, len(data))
            self.assertEqual("extra", data[2]["key"])
            self.assertEqual("Сәлем", data[0]["result"])
            self.assertEqual("Сау бол", data[1]["result"])
            self.assertEqual(original, target.read_text(encoding="utf-8"))
            approved = json.loads((root / "result/intl_kk_fixed.arb").read_text(encoding="utf-8"))
            draft = json.loads((root / "result/intl_kk_draft.arb").read_text(encoding="utf-8"))
            self.assertEqual("", approved["two"])
            self.assertEqual("Сау бол", draft["two"])

    def test_reviewed_correction_enters_both_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "input"
            folder.mkdir()
            (folder / "intl_ru.arb").write_text('{"key":"Привет"}', encoding="utf-8")
            (folder / "intl_kk.arb").write_text('{"key":""}', encoding="utf-8")
            (folder / "corrections.csv").write_text("key,translation,reviewed_by_human\nkey,Сәлем,true\n", encoding="utf-8")
            with patch("workflow.render_report"), patch("proposal_loader.load_proposals", return_value={}), patch("proposal_loader.load_proposal_details", return_value={}):
                run(folder, root / "result", ai_limit=0)
            for name in ("intl_kk_fixed.arb", "intl_kk_draft.arb"):
                result = json.loads((root / "result" / name).read_text(encoding="utf-8"))
                self.assertEqual("Сәлем", result["key"])
                self.assertIn("reviewed_by_human=true", result["@key"]["description"])

    def test_missing_input_reports_what_to_add(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "intl_ru.arb"):
                find_inputs(Path(directory))
