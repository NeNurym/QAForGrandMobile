import csv
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from merge_reviews import merge_reviews


def workbook(path: Path, keys: list[str], reviewed: bool = False) -> None:
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rows = "".join(
        f'<row r="{index}"><c r="A{index}" t="inlineStr"><is><t>{key}</t></is></c>'
        f'<c r="H{index}" t="inlineStr"><is><t>Аударма</t></is></c>'
        f'<c r="I{index}" t="inlineStr"><is><t>{"Да" if reviewed else "Нет"}</t></is></c></row>'
        for index, key in enumerate(keys, 6)
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{ns}"><sheetData>{rows}</sheetData></worksheet>')


class MergeReviewTests(unittest.TestCase):
    def test_merge_preserves_approval_and_reviewer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            full, part1, part2, out = (root / name for name in ("full.xlsx", "1.xlsx", "2.xlsx", "merged.csv"))
            workbook(full, ["a", "b"])
            workbook(part1, ["a"], reviewed=True)
            workbook(part2, ["b"])
            self.assertEqual((2, 1), merge_reviews([part1, part2], full, out))
            with out.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(["a", "b"], [row["key"] for row in rows])
            self.assertEqual(["true", "false"], [row["reviewed_by_human"] for row in rows])
            self.assertEqual(["Проверяющий 1", "Проверяющий 2"], [row["reviewer"] for row in rows])

    def test_duplicate_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            full, part1, part2 = (root / name for name in ("full.xlsx", "1.xlsx", "2.xlsx"))
            for path in (full, part1, part2):
                workbook(path, ["a"])
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                merge_reviews([part1, part2], full, root / "merged.csv")


if __name__ == "__main__":
    unittest.main()
