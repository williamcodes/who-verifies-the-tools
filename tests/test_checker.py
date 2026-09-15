import unittest

from experiment import contract_checker as checker


class TestDisclosureBoundaries(unittest.TestCase):
    def test_scope_disclosure_does_not_excuse_full_text_claim(self):
        case = {"input": {"scan_capped": True}}
        self.assertTrue(checker.check_f1("FULL text; first 1,000,000 characters", case))
        self.assertFalse(checker.check_f1("first 1,000,000 characters", case))
        self.assertFalse(
            checker.check_f1("FULL text", {"input": {"scan_capped": False}})
        )

    def test_completeness_requires_total_or_disclosure_in_header(self):
        case = {"input": [{}] * 20, "facts": {"true_total": 1920, "page_limit": 20}}
        self.assertTrue(checker.check_f2("Found 20 documents\nDated 1920", case))
        self.assertTrue(checker.check_f2("Found 20 documents\nnot exhaustive", case))
        self.assertFalse(checker.check_f2("Showing 20 of 1,920 documents", case))
        self.assertFalse(checker.check_f2("Found 20 documents; not exhaustive", case))
        case["facts"]["true_total"] = 20
        self.assertFalse(checker.check_f2("Found 20 documents", case))

    def test_estimate_label_covers_nearby_page_only(self):
        self.assertFalse(checker.check_f3("ESTIMATED page 3 of 8", {}))
        self.assertTrue(checker.check_f3("page 3 of 8", {}))
        self.assertTrue(checker.check_f3("ESTIMATED " + "x" * 21 + " page 3 of 8", {}))
        self.assertTrue(checker.check_f3("ESTIMATED page 3 of 8; page 4 of 8", {}))

    def test_identifier_namespace_is_required_for_each_bracketed_id(self):
        self.assertFalse(checker.check_f4("[doc:10] [scan:11]", {}))
        self.assertTrue(checker.check_f4("[doc:10] [11]", {}))

    def test_checker_does_not_verify_truth_of_disclosures(self):
        # This documented limitation is intentional frozen behavior.
        self.assertFalse(checker.check_f3("ESTIMATED page 999 of 2", {}))
        self.assertFalse(checker.check_f4("[scan:999999]", {}))
