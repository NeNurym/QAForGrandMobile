import tempfile
import json
import unittest
from pathlib import Path

from report_ui import group_findings, render_report, report_rows


class ReportUITests(unittest.TestCase):
    def test_groups_findings_by_key_and_orders_urgent_first(self):
        rows = [
            {"key": "a", "issue_type": "length_overflow", "severity": "medium", "source": "A", "target": "B"},
            {"key": "b", "issue_type": "untranslated", "severity": "high", "source": "C", "target": ""},
            {"key": "a", "issue_type": "orthography", "severity": "medium", "source": "A", "target": "B"},
        ]
        groups = group_findings(rows)
        self.assertEqual(["b", "a"], [group["key"] for group in groups])
        self.assertEqual(2, len(groups[1]["issues"]))

    def test_report_escapes_arb_text_and_shows_guided_navigation(self):
        rows = [{"key": 'bad"key', "issue_type": "untranslated", "severity": "high",
                 "source": "<script>alert(1)</script>", "target": "", "evidence": "Missing"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.html"
            render_report(rows, path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("\\u003cscript\\u003ealert(1)\\u003c/script\\u003e", text)
            self.assertNotIn("<script>alert(1)</script>", text)
            payload = json.loads(text.split('<script id="report-data" type="application/json">')[1].split('</script>')[0])
            self.assertEqual('bad"key', payload['rows'][0]['key'])
            self.assertIn('id="rows"', text)
            self.assertNotIn('<details>', text)
            self.assertEqual(1, text.count('class="toolbar"'))

    def test_all_rows_changes_and_approval_are_distinct(self):
        rows = report_rows([], {'a': 'A', 'b': 'B', '@@locale': 'ru'}, {'a': 'new', 'b': 'same'},
                           {'a': 'old', 'b': 'same'}, {'a': ['proposal']})
        self.assertEqual(2, len(rows))
        by_key = {row['key']: row for row in rows}
        self.assertEqual('changed', by_key['a']['status'])
        self.assertEqual('clear', by_key['b']['status'])
        self.assertEqual('old', by_key['a']['before'])
        self.assertEqual(['proposal'], by_key['a']['proposals'])
        approved = report_rows([], {'a': 'A'}, {'a': 'new'}, {'a': 'old'}, reviewed_keys={'a'})
        self.assertEqual('reviewed', approved[0]['status'])


if __name__ == "__main__":
    unittest.main()
