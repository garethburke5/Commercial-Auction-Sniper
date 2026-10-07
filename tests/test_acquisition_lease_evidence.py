import unittest

from acquisition_lease_evidence import extract_lease_evidence
from legal_pack_engine import DocType, PackDocument


def lease(name, pages):
    return PackDocument(name, DocType.LEASE, "\n".join(pages), "test-hash",
                        {"pages": [{"page": i + 1, "text": p, "ocr": False} for i, p in enumerate(pages)]})


class LeaseEvidenceTests(unittest.TestCase):
    def test_individual_tenants_and_separate_demises(self):
        docs = [lease("Unit A lease.pdf", ["(2) JANE DOE of 1 Example Road (Tenant). Annual Rent: rent at a rate of £12,000.00 per annum."]),
                lease("Unit B lease.pdf", ["(2) ADAM JONES and JULIA JONES of 9 Example Road (Tenant). Annual Rent: rent at a rate of £7,000 per annum."])]
        rows = extract_lease_evidence(docs)["leases"]
        self.assertEqual([r["annual_rent"] for r in rows], [12000, 7000])
        self.assertEqual(rows[1]["tenant"], "ADAM JONES and JULIA JONES")
        self.assertEqual(rows[0]["evidence"][0]["page"], 1)

    def test_break_requires_operative_power_and_preserves_edited_date(self):
        doc = lease("Lease.pdf", ["CONTENTS Break Clause............................34",
            "TENANT'S BREAK CLAUSE Break Date: [2march April] 2029. Break Notice: written notice to terminate this lease. "
            "The Tenant may terminate this lease on the Break Date by serving the Break Notice on the Landlord not less than six months before the Break Date. "
            "The Break Notice shall have no effect if at the Break Date rent is unpaid or there are subsisting subleases."])
        result = extract_lease_evidence([doc])
        b = result["leases"][0]["breaks"]
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0]["date_raw"], "[2march April] 2029")
        self.assertTrue(b[0]["uncertain"])
        self.assertEqual(b[0]["evidence"][0]["page"], 2)
        self.assertIn("six months", b[0]["notice_raw"])
        self.assertTrue(any(f["title"] == "Edited lease dates need confirmation" for f in result["findings"]))

    def test_flat_ground_rent_never_certifies_current_receipts(self):
        doc = lease("Flat lease.pdf", ["The term of 125 years from and including 1 June 2010. The Flat is a residential flat. "
            "'The Initial Rent' means the yearly sum of One hundred pounds (£100.00). "
            "The Review Date means any one of 1 June 2035 and every twenty-fifth anniversary of that date during the Term.",
            "For the succeeding period of 25 years from and including the said first Review Date after the date of this Lease the Rent shall be twice the Initial Rent. "
            "For each succeeding period of 25 years during the Term the Rent shall be twice the amount payable in respect of the immediately preceding period of 25 years."])
        row = extract_lease_evidence([doc])["leases"][0]
        self.assertEqual(row["ground_rent"]["initial_amount"], 100)
        self.assertIsNone(row["ground_rent"]["current_amount"])
        self.assertIn("twice", row["ground_rent"]["review_wording"])
        self.assertEqual(row["interest"], "Residential long lease")

    def test_receipt_ledger_not_promoted_to_lease(self):
        doc = PackDocument("Rent receipts.pdf", DocType.TENANCY_SCHEDULE, "Annual Rent: £500. Tenant A", "hash")
        self.assertEqual(extract_lease_evidence([doc]), {"leases": [], "findings": []})

    def test_generic_guarantee_and_assignment_deposit_not_security(self):
        doc = lease("Lease.pdf", ["Annual Rent: £10,000. The Guarantor guarantees the tenant covenants. "
            "An assignee shall enter into a rent deposit deed for six months rent. "
            "The parties agree that the provisions of sections 24 to 28 of the LTA 1954 are excluded in relation to the tenancy created by this Lease."])
        row = extract_lease_evidence([doc])["leases"][0]
        self.assertEqual(row["rent_deposit"], "No existing deposit established from the lease text")
        self.assertFalse(row["security"]["verified_procedure"])

    def test_landlord_structure_and_flat_charge_allocation_remain_evidenced(self):
        doc = lease("Flat lease.pdf", [
            "The Landlord must: repair and where necessary renew the foundations, roof and roof structure of the Building;",
            "The Tenant's Proportion means (subject always to paragraph 8.3) in the case of expenditure relating to the Common Parts one-half of the amount; "
            "in the case of windows and doors the whole amount; in the case of all other items of Expenditure 30%."])
        row = extract_lease_evidence([doc])["leases"][0]
        self.assertTrue(row["repairs"])
        self.assertIn("30%", row["service_charge"][0]["text"])
        self.assertEqual(row["service_charge"][0]["evidence"][0]["page"], 2)


if __name__ == "__main__":
    unittest.main()
