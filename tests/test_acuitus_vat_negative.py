import unittest
from collectors.core import parse_vat

class AcuitusVatNegativeTests(unittest.TestCase):
    def test_not_elected_for_vat_is_not_applicable(self):
        self.assertEqual(parse_vat("The property is Not Elected for VAT"), "NOT APPLICABLE")

if __name__ == "__main__":
    unittest.main()
