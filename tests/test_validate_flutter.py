import json
import tempfile
import unittest
from pathlib import Path

from validate_flutter import normalized_arb_copies


class FlutterCopyTests(unittest.TestCase):
    def test_normalization_changes_only_temporary_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.arb"
            target = root / "target.arb"
            source.write_text('{"@@locale":"ru","UNeedHelp":"Помощь","inventoryEquipped@description":"Описание"}', encoding="utf-8")
            target.write_text('{"@@locale":"kk","UNeedHelp":"Көмек","@UNeedHelp":{"description":"hint"},"inventoryEquipped@description":"Сипаттама"}', encoding="utf-8")
            before = target.read_bytes()
            mapping = normalized_arb_copies(source, target, root)
            self.assertEqual("uNeedHelp", mapping["UNeedHelp"])
            self.assertEqual("inventoryEquipped_description", mapping["inventoryEquipped@description"])
            output = json.loads((root / "intl_kk.arb").read_text("utf-8"))
            self.assertIn("@uNeedHelp", output)
            self.assertEqual(before, target.read_bytes())


if __name__ == "__main__":
    unittest.main()
