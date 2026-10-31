import re
import unittest

from qwen_glossary_proposals import build_prompt, contains_kazakh_term, structurally_safe, terms_for_source


class QwenGlossaryProposalTests(unittest.TestCase):
    def test_rejects_changed_placeholder_or_number(self):
        source = "Получено {count} наград: 10"
        self.assertTrue(structurally_safe(source, "Алынды {count} сыйлық: 10"))
        self.assertFalse(structurally_safe(source, "Алынды {number} сыйлық: 10"))
        self.assertFalse(structurally_safe(source, "Алынды {count} сыйлық: 11"))

    def test_prompt_marks_draft_glossary(self):
        term = {"ru": "награда", "kk": "сыйлық", "approved": False,
                "strict": True, "alternatives": "марапат",
                "pattern": re.compile("наград", re.IGNORECASE)}
        selected = terms_for_source("Получите награду", [term])
        prompt = build_prompt("rewardKey", "Получите награду", "Get reward", selected)
        self.assertIn("Черновые игровые термины", prompt)
        self.assertIn("награда = сыйлық", prompt)

    def test_contextual_term_offers_alternatives_without_forcing_one(self):
        term = {"ru": "ставка", "kk": "бәс", "approved": False, "strict": False,
                "alternatives": "ставка|бәс тігу", "pattern": re.compile("ставк", re.IGNORECASE)}
        prompt = build_prompt("bet", "Новая ставка", "New bet", [term])
        self.assertIn("Неоднозначные игровые слова", prompt)
        self.assertIn("бәс / ставка / бәс тігу", prompt)

    def test_conjugated_verb_still_matches_glossary_lemma(self):
        self.assertTrue(contains_kazakh_term("Көлігіңізді жақсарттыңыз", "жақсарту"))
        self.assertFalse(contains_kazakh_term("Көлігіңізді өшірдіңіз", "жақсарту"))


if __name__ == "__main__":
    unittest.main()
