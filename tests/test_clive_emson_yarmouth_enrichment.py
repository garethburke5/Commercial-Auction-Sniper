import unittest

from collectors.clive_emson_resilient import _clive_facts


YARMOUTH_TEXT = """
Lot 41 Commercial Investment With Share Of Freehold.
Corner Shop, Eremue Court, Bridge Road, Yarmouth, Isle Of Wight, PO41 0PH.
Currently let at £7,000 per annum. Category Commercial Investment. Tenure Share of Freehold.
This attractive building is situated in the centre of Yarmouth, a popular residential location at the western end of the Isle of Wight and home to the Wightlink car ferry terminal between the Isle of Wight and Lymington which results in a significant tourist footfall.
The majority of Eremue Court is residential accommodation but the ground floor corner unit comprises a retail shop which has traded very successfully in recent years as a fudge manufacturer and retailer.
The commercial unit is held under the terms of a long leasehold but includes a share in the freehold for the building.
Tenancy Held under the terms of a commercial lease expiring 25th March 2028 at a current rental of £7,000 per annum.
Tenure Remainder of a 189-year lease from 12th August 1966.
Auctioneer's Note We are advised the freehold of the building is held by the long lessees with the share of freehold transferrable on completion.
"""


class CliveEmsonYarmouthEnrichmentTests(unittest.TestCase):
    def test_extracts_share_of_freehold_and_lease_facts(self):
        facts = _clive_facts(YARMOUTH_TEXT, "Lot 41 Commercial Investment With Share Of Freehold")
        self.assertEqual(facts.get("property_type"), "Retail")
        self.assertEqual(facts.get("tenure"), "Share of Freehold")
        self.assertEqual(facts.get("occupation"), "Let")
        self.assertEqual(facts.get("lease_expiry"), "25th March 2028")
        self.assertEqual(facts.get("lease_term"), "189 years")
        self.assertEqual(facts.get("lease_start"), "12th August 1966")
        self.assertIn("significant tourist footfall", facts.get("pitch", ""))
        self.assertIn("Share of freehold transfers on completion", facts.get("pitch", ""))


if __name__ == "__main__":
    unittest.main()
