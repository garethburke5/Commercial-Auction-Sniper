import unittest

from acquisition_lease_evidence import extract_lease_evidence
from legal_pack_engine import DocType, PackDocument


def lease(name, pages):
    return PackDocument(name, DocType.LEASE, "\n".join(pages), "test-hash",
                        {"pages": [{"page": i + 1, "text": p, "ocr": False} for i, p in enumerate(pages)]})


class LeaseEvidenceTests(unittest.TestCase):
    def form_particulars(self):
        return ('The Law Society. DATE OF LEASE 20th April 20 26. '
                'LANDLORD Example Estates Ltd ADDRESS 9 Other Road. '
                'TENANT Example Charity No 123456 ADDRESS 15 Other Street. '
                'GUARANTOR ADDRESS POSTCODE COMPANY NO. '
                'PROPERTY Ground Floor 71 Example Road, Town, EX1 1AB '
                'shown edged red on the attached plan being part of the Building. '
                'TERM FOR WHICH oS THE PROPERTY IS c LEASED '
                'From and including 13th April 20 26 = Toand including 12th April 20 31 = '
                'PARKING No more than n/a vehicles USE ALLOWED Retail '
                'RENT Twelve thousand Pounds ea 12,000.00 ) a year, subject to increase. '
                'FIRST PAYMENT DATE 13 April 2026. The Landlord lets the property to the Tenant.')

    def test_law_society_form_preserves_unit_tenant_rent_dates_and_source_page(self):
        row = extract_lease_evidence([lease('Business lease.pdf', [self.form_particulars()])])['leases'][0]
        self.assertEqual(row['annual_rent'], 12000)
        self.assertEqual(row['tenant'], 'Example Charity')
        self.assertEqual(row['demise'], 'Ground Floor 71 Example Road, Town, EX1 1AB')
        self.assertEqual(row['lease_date'], '20 April 2026')
        self.assertEqual(row['term']['text'], 'From and including 13 April 2026 to and including 12 April 2031')
        self.assertTrue(all(e['page'] == 1 for e in row['evidence']))
        self.assertNotIn('9 Other Road', str(row['evidence']))
        self.assertEqual(row['guarantee'], 'No separately identified guarantor established')

    def test_form_amount_does_not_override_a_conflicting_rent_in_the_document(self):
        row = extract_lease_evidence([lease('Business lease.pdf', [self.form_particulars(),
            'Annual Rent: £13,000 per annum.'])])['leases'][0]
        self.assertIsNone(row['annual_rent'])
        self.assertTrue(row['rent_conflicted'])

    def test_form_requires_annual_basis_and_correct_form_not_a_quoted_annex(self):
        for text in [self.form_particulars().replace('a year', 'a month'),
                     self.form_particulars().replace('The Law Society', 'Some particulars')]:
            row = extract_lease_evidence([lease('Unknown.pdf', [text])])['leases'][0]
            self.assertIsNone(row['annual_rent'])
        row = extract_lease_evidence([lease('Renewal.pdf', ['LEASE. Unclear renewal particulars.',
            self.form_particulars()])])['leases'][0]
        self.assertIsNone(row.get('demise'))
        self.assertIsNone(row['annual_rent'])

    def test_impossible_boxed_date_does_not_create_a_lease_deadline(self):
        text = self.form_particulars().replace('12th April 20 31', '31st February 20 31')
        row = extract_lease_evidence([lease('Business lease.pdf', [text])])['leases'][0]
        self.assertIsNone(row['term'])

    def test_service_charge_cap_keeps_indexation_and_scope(self):
        doc=lease('Shop lease.pdf', ['LEASE. Service Charge: a fair proportion of structural repair costs including managing agent costs, provided that such costs will be capped at £3,200.00 per annum until the first anniversary and thereafter increase by Retail Price Index per annum. After 8-year anniversary there is no cap. Service Media: pipes.'])
        result=extract_lease_evidence([doc])
        entry=result['leases'][0]['service_charge'][0]
        self.assertIn('Retail Price Index',entry['text'])
        self.assertIn('After 8-year anniversary there is no cap',entry['text'])
        self.assertEqual(entry['evidence'][0]['page'],1)
        self.assertIn('scope',entry['basis'].lower())

    def test_explicit_substitution_separates_new_rent_from_annexed_old_lease(self):
        doc = lease('Renewal of 8 Example Road.pdf', [
            'Annual Rent: rent at a rate of £27,500 per annum.',
            'This Lease shall reserve the Annual Rent instead of, and not in addition to, the Existing Lease Annual Rent.',
            'ANNEX 1 Certified copy of the Existing Lease',
            'Yearly Rent: £32,000 per annum.'])
        result = extract_lease_evidence([doc])
        row = result['leases'][0]
        self.assertEqual(row['annual_rent'], 27500)
        self.assertEqual(row['rent_substitution']['earlier_amounts'], [32000])
        self.assertEqual({e['page'] for e in row['rent_substitution']['evidence']}, {1, 2, 3, 4})
        self.assertFalse(row.get('rent_conflicted'))
        self.assertIn('not proof of payment', result['findings'][0]['meaning'])

    def test_later_rent_is_not_selected_without_explicit_replacement_and_annex_scope(self):
        for pages in [
            ['Annual Rent: rent at a rate of £27,500 per annum.',
             'ANNEX 1 Certified copy of the Existing Lease', 'Yearly Rent: £32,000 per annum.'],
            ['Annual Rent: rent at a rate of £27,500 per annum.',
             'This Lease shall reserve the Annual Rent instead of, and not in addition to, the Existing Lease Annual Rent.',
             'Yearly Rent: £32,000 per annum.'],
            ['Annual Rent: rent at a rate of £27,500 per annum. Initial Rent: £25,000 per annum.',
             'This Lease shall reserve the Annual Rent instead of, and not in addition to, the Existing Lease Annual Rent.',
             'ANNEX 1 Certified copy of the Existing Lease', 'Yearly Rent: £32,000 per annum.'],
        ]:
            with self.subTest(pages=pages):
                row = extract_lease_evidence([lease('Renewal.pdf', pages)])['leases'][0]
                self.assertIsNone(row['annual_rent'])
                self.assertTrue(row['rent_conflicted'])

    def test_replacement_clause_from_another_document_cannot_resolve_rent(self):
        docs = [lease('Lease.pdf', ['Annual Rent: rent at a rate of £27,500 per annum.',
                 'ANNEX 1 Certified copy of the Existing Lease', 'Yearly Rent: £32,000 per annum.']),
                lease('Other lease.pdf', ['This Lease shall reserve the Annual Rent instead of, and not in addition to, the Existing Lease Annual Rent.'])]
        self.assertTrue(extract_lease_evidence(docs)['leases'][0]['rent_conflicted'])

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
