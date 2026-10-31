import unittest

from model_proposals import safe_candidate


class ProposalTests(unittest.TestCase):
    def test_rejects_broken_arb_syntax(self):
        self.assertFalse(safe_candidate("Привет {name}", "Сәлем name"))
        self.assertFalse(safe_candidate("<g>Бонус</g>", "Бонус"))
        self.assertTrue(safe_candidate("Привет {name}", "Сәлем {name}"))


if __name__ == "__main__":
    unittest.main()
