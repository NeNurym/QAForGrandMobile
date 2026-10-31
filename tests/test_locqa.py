import csv
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from locqa import apply_corrections, apply_glossary_review, approved_empty_keys, audit, check, human_reviewed_keys, read_arb, read_review_xlsx


class LocqaTests(unittest.TestCase):
    def test_duplicate_comments_and_spans(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "intl_kk.arb"
            path.write_text('{"@@locale":"kk","@@comment":"A","a":"бір","@@comment":"B","b":"екі"}', encoding="utf-8")
            raw, entries, values = read_arb(path)
            self.assertEqual(2, sum(e.key == "@@comment" for e in entries))
            self.assertEqual({"a": "бір", "b": "екі"}, values)
            self.assertEqual(raw[entries[2].start:entries[2].end], '"бір"')

    def test_duplicate_translation_uses_last_value(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "intl_kk.arb"
            path.write_text('{"@@locale":"kk","a":"бір","a":"екі"}', encoding="utf-8")
            _, entries, values = read_arb(path)
            self.assertEqual(2, sum(e.key == "a" for e in entries))
            self.assertEqual("екі", values["a"])

    def test_structural_findings(self):
        source = {"a": "Привет {name}", "b": "Неизвестная ошибка", "c": "{count, plural, one{1} other{#}}"}
        target = {"a": "Сәлем, name", "b": "Неизвестная ошибка", "c": "{count, plural, one{1}}"}
        findings = check(source, target, [])
        pairs = {(f["key"], f["issue_type"]) for f in findings}
        self.assertIn(("a", "placeholder_mismatch"), pairs)
        self.assertIn(("b", "same_as_source"), pairs)
        self.assertIn(("c", "plural_mismatch"), pairs)

    def test_suspect_kazakh_phrase_is_review_candidate(self):
        findings = check({"a": "Получай токены"}, {"a": "Күдікті тіркес"}, [], suspect_phrases=("күдікті тіркес",))
        self.assertIn("machine_translation_suspect", {f["issue_type"] for f in findings})

    def test_apply_marks_review_and_preserves_comments(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "intl_kk.arb"
            source.write_text('{"@@locale":"kk","@@comment":"A","a":"ескі","@@comment":"B","b":"екі"}', encoding="utf-8")
            corrections = root / "corrections.csv"
            corrections.write_text("key,translation,reviewed_by_human\na,жаңа,true\n", encoding="utf-8")
            output = root / "intl_kk_fixed.arb"
            changed, reviewed = apply_corrections(source, corrections, output)
            raw, entries, values = read_arb(output)
            self.assertEqual((1, 1), (changed, reviewed))
            self.assertEqual("жаңа", values["a"])
            self.assertEqual(2, sum(e.key == "@@comment" for e in entries))
            self.assertIn("QA: reviewed_by_human=true", raw)
            self.assertEqual({"a"}, human_reviewed_keys(entries))
            findings = check({"a": "Привет {name}"}, values, [], reviewed_keys=human_reviewed_keys(entries))
            self.assertTrue(findings)
            self.assertTrue(all(f["reviewed_by_human"] for f in findings if f["key"] == "a"))

    def test_apply_adds_missing_key_from_source(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "intl_ru.arb"
            source.write_text('{"@@locale":"ru","a":"Привет","b":"Пока"}', encoding="utf-8")
            target = root / "intl_kk.arb"
            target.write_text('{"@@locale":"kk","a":"Сәлем"}', encoding="utf-8")
            corrections = root / "corrections.csv"
            corrections.write_text("key,translation,reviewed_by_human\nb,Сау бол,true\n", encoding="utf-8")
            output = root / "intl_kk_fixed.arb"
            changed, reviewed = apply_corrections(target, corrections, output, source)
            _, _, values = read_arb(output)
            self.assertEqual((1, 1), (changed, reviewed))
            self.assertEqual("Сау бол", values["b"])

    def test_apply_only_reviewed_skips_unverified_drafts(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            baseline = root / "intl_kk.arb"
            baseline.write_text('{"a":"ескі","b":"ескі"}', encoding="utf-8")
            corrections = root / "corrections.csv"
            corrections.write_text("key,translation,reviewed_by_human\na,жаңа,true\nb,жаңа,false\n", encoding="utf-8")
            output = root / "fixed.arb"
            self.assertEqual((1, 1), apply_corrections(baseline, corrections, output, only_reviewed=True))
            values = read_arb(output)[2]
            self.assertEqual("жаңа", values["a"])
            self.assertEqual("ескі", values["b"])

    def test_apply_rejects_reviewed_broken_placeholder(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "ru.arb"
            baseline = root / "kk.arb"
            corrections = root / "corrections.csv"
            source.write_text('{"a":"Привет {name}"}', encoding="utf-8")
            baseline.write_text('{"a":"Сәлем {name}"}', encoding="utf-8")
            corrections.write_text("key,translation,reviewed_by_human\na,Сәлем,true\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changes placeholders"):
                apply_corrections(baseline, corrections, root / "fixed.arb", source)

    def test_review_xlsx_reads_excel_shared_and_inline_strings(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "review.xlsx"
            ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
            sheet = f'''<worksheet xmlns="{ns}"><sheetData><row r="6">
              <c r="A6" t="inlineStr"><is><t>hello</t></is></c>
              <c r="F6" t="s"><v>0</v></c>
              <c r="G6" t="inlineStr"><is><t>Да</t></is></c>
            </row></sheetData></worksheet>'''
            shared = f'<sst xmlns="{ns}"><si><t>Сәлем</t></si></sst>'
            with ZipFile(path, "w") as archive:
                archive.writestr("xl/worksheets/sheet1.xml", sheet)
                archive.writestr("xl/sharedStrings.xml", shared)
            self.assertEqual([{"key": "hello", "translation": "Сәлем", "reviewed_by_human": "true", "comment": ""}], read_review_xlsx(path))

    def test_review_xlsx_reads_three_option_layout(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "review_ai.xlsx"
            ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
            sheet = f'''<worksheet xmlns="{ns}"><sheetData><row r="6">
              <c r="A6" t="inlineStr"><is><t>hello</t></is></c>
              <c r="E6" t="inlineStr"><is><t>Бір</t></is></c>
              <c r="H6" t="inlineStr"><is><t>Сәлем</t></is></c>
              <c r="I6" t="inlineStr"><is><t>Да</t></is></c>
              <c r="J6" t="inlineStr"><is><t>Тексерілді</t></is></c>
            </row></sheetData></worksheet>'''
            with ZipFile(path, "w") as archive:
                archive.writestr("xl/worksheets/sheet1.xml", sheet)
            self.assertEqual([{"key": "hello", "translation": "Сәлем", "reviewed_by_human": "true", "comment": "Тексерілді"}], read_review_xlsx(path))

    def test_audit_requires_review_and_complete_keys(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "intl_ru.arb"
            baseline = root / "intl_kk.arb"
            fixed = root / "intl_kk_fixed.arb"
            corrections = root / "corrections.csv"
            source.write_text('{"@@locale":"ru","a":"Привет","b":"Пока"}', encoding="utf-8")
            baseline.write_text('{"@@locale":"kk","a":"Сәлем"}', encoding="utf-8")
            corrections.write_text("key,translation,reviewed_by_human\nb,Сау бол,false\n", encoding="utf-8")
            apply_corrections(baseline, corrections, fixed, source)
            result = audit(source, baseline, fixed)
            self.assertEqual(1, result["blockers"]["changed_not_human_reviewed"])
            self.assertEqual(0, result["blockers"]["untranslated"])
            self.assertFalse(result["ready_for_flutter_test"])

    def test_human_approved_intentional_empty(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "intl_ru.arb"
            baseline = root / "intl_kk.arb"
            fixed = root / "intl_kk_fixed.arb"
            corrections = root / "corrections.csv"
            source.write_text('{"@@locale":"ru","a":"в"}', encoding="utf-8")
            baseline.write_text('{"@@locale":"kk","a":""}', encoding="utf-8")
            corrections.write_text("key,translation,reviewed_by_human,comment\na,,true,Postposition omitted in Kazakh\n", encoding="utf-8")
            apply_corrections(baseline, corrections, fixed, source)
            _, entries, values = read_arb(fixed)
            self.assertEqual({"a"}, approved_empty_keys(entries))
            self.assertEqual("", values["a"])
            self.assertTrue(audit(source, baseline, fixed)["ready_for_flutter_test"])

    def test_latest_review_marker_controls_status(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "intl_kk.arb"
            path.write_text('{"a":"","@a":{"description":"QA: reviewed_by_human=true; empty_intentional=true; reason=context | QA: reviewed_by_human=false"}}', encoding="utf-8")
            _, entries, _ = read_arb(path)
            self.assertEqual(set(), human_reviewed_keys(entries))
            self.assertEqual(set(), approved_empty_keys(entries))

    def test_glossary_review_updates_approved_term(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            glossary = root / "glossary.csv"
            glossary.write_text("ru,kk,en,comment,ru_stem,kk_stems,reviewed_by_human,enforce,scope\nкейс,кейс,case,Game term,кейс,кейс,false,true,\n", encoding="utf-8")
            workbook = root / "review.xlsx"
            ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
            sheet = f'''<worksheet xmlns="{ns}"><sheetData><row r="6">
              <c r="A6" t="inlineStr"><is><t>кейс</t></is></c>
              <c r="C6" t="inlineStr"><is><t>кейс|сандық</t></is></c>
              <c r="F6" t="inlineStr"><is><t>кейс</t></is></c>
              <c r="G6" t="inlineStr"><is><t>Да</t></is></c>
            </row></sheetData></worksheet>'''
            with ZipFile(workbook, "w") as archive:
                archive.writestr("xl/worksheets/sheet2.xml", sheet)
            output = root / "checked.csv"
            self.assertEqual(1, apply_glossary_review(glossary, workbook, output))
            self.assertIn("кейс|сандық,true", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
