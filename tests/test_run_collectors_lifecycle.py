import unittest

from run_collectors import _is_terminal, _normal_status


class RunCollectorsLifecycleTests(unittest.TestCase):
    def test_terminal_statuses_are_recognised(self):
        for status in ("SOLD PRIOR", "withdrawn", "Withdrawn Prior", "ARCHIVED", "completed"):
            with self.subTest(status=status):
                self.assertTrue(_is_terminal({"status": status}))

    def test_current_and_stale_are_not_terminal(self):
        self.assertFalse(_is_terminal({"status": "CURRENT"}))
        self.assertFalse(_is_terminal({"status": "STALE SOURCE"}))

    def test_status_normalisation_is_stable(self):
        self.assertEqual(_normal_status("sold_prior"), "SOLD PRIOR")
        self.assertEqual(_normal_status(" withdrawn prior "), "WITHDRAWN PRIOR")


if __name__ == "__main__":
    unittest.main()
