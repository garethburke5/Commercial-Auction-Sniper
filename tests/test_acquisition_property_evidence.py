"""Outcomes must survive negative replies, old dates and detached table columns."""
from acquisition_property_evidence import extract_property_evidence
from legal_pack_engine import make_document


def doc(name, *pages):
    return make_document(name, "\n".join(pages), metadata={"pages": [
        {"page": n, "text": text, "ocr": False} for n, text in enumerate(pages, 1)
    ]})


def test_insurance_exclusion_requires_policy_not_lease_promise():
    lease = doc("Lease.txt", "Landlord to insure. Subsidence Not Included in this sample policy wording.")
    policy = doc("Certificate.txt", "Policy Certificate. Subsidence extension: Not Included. Date this cover starts: 01/01/2024 Date this cover expires: 31/12/2024")
    findings = extract_property_evidence([lease, policy])
    assert len(findings) == 1
    assert "supplied" in findings[0]["found"] and "stated policy period" in findings[0]["meaning"]
    assert {e["document"] for e in findings[0]["evidence"]} == {"Certificate.txt"}


def test_models_are_not_claims_of_actual_flooding_or_subsidence():
    document = doc("Groundsure search.txt", "A high risk of groundwater flooding has been identified at a building/structure level with a significant likelihood of occurrence. Water emergence is expected to impact basements, underground services, and potentially ground floors, leading to notable disruption or damage.",
                   "The property, or an area within 50m of the property, has a moderate to high potential for natural ground subsidence.")
    findings = extract_property_evidence([document])
    assert len(findings) == 2
    assert "not confirmation" in findings[0]["meaning"]
    assert "not evidence of actual subsidence" in findings[1]["meaning"]
    assert [f["evidence"][0]["page"] for f in findings] == [1, 2]
    boilerplate = doc("Groundsure search.txt", "Groundwater flooding is a flood risk. High means significant likelihood. The meaning of subsidence is ground movement.")
    assert extract_property_evidence([boilerplate]) == []


def test_fire_actions_stay_at_assessment_date_and_not_assumed_complete():
    document = doc("Fire report.txt", "FIRE Example Consulting RISK ASSESSMENT Date of assessment: 02/03/2021 Recommended review date: March 2022",
                   "SUMMARY OF FINDINGS Total number of actions identified: 9 overall risk of harm is deemed to be: FIRE SAFETY MEDIUM",
                   "Upgrade automatic fire detection and warning system in the common areas. Undertake remedial works to vertical penetrations penetrations in the locations observed where identified. Verify whether fixed wiring * certificate is available and up to date. Install or replace intumescent strips observed missing and/or smoke seals.")
    finding, = extract_property_evidence([document])
    assert "02/03/2021" in finding["found"] and "9 actions" in finding["found"]
    assert "March 2022" in finding["found"]
    assert "Neither current defects nor completion" in finding["meaning"]
    assert "alarm upgrading" in finding["found"] and "fire stopping" in finding["found"]
    assert "electrical certification" in finding["found"] and "fire-door seals" in finding["found"]


def test_cpse_reply_and_attached_asbestos_are_reconciled_without_clearance():
    cpse = doc("CPSE7.txt", "CPSE.7 General short form. 4.4 Please supply copies of the most recent asbestos survey and asbestos management plan for the Property, together with any other relevant information you hold. None available.")
    survey = doc("Old survey.txt", "Asbestos Inspection Report. No suspect materials were detected within the remit of this survey.")
    findings = extract_property_evidence([cpse, survey])
    assert len(findings) == 2
    assert "Separate asbestos inspection reports" in findings[0]["found"]
    assert "does not establish an asbestos-free" in findings[0]["meaning"]
    assert len(findings[0]["evidence"]) == 2
    assert "must not overwrite a positive" in findings[1]["meaning"]


def test_asbestos_glossary_and_risk_legend_do_not_become_positive_sample():
    glossary = doc("Asbestos.txt", "Asbestos Inspection Report. Key: Chrysotile White Asbestos Amosite Brown Asbestos Crocidolite Blue Asbestos. HIGH RISK MATERIAL REQUIRING URGENT ATTENTION 18 points or more.")
    positive = doc("Asbestos sample.txt", "Asbestos Inspection Report", "Sample No. A123 Location. Store Room Element. Panel Asbestos Type. Trace Crocidolite/Low Chrysotile Material Score: 6 Overall Score: 10")
    assert extract_property_evidence([glossary]) == []
    finding, = extract_property_evidence([positive])
    assert "Trace Crocidolite/Low Chrysotile" in finding["found"]
    assert "current demise" in finding["meaning"]
    assert finding["requires_visual_review"]


def test_cpse_epc_page_continuation_must_be_immediate():
    document = doc("CPSE7.txt", "CPSE.7 10.4 Please supply a valid Energy Performance Certificate. EPC for the commercial premises to footer page 10", "follow. 10.5 Other questions.")
    findings = extract_property_evidence([document])
    assert len(findings) == 1
    assert [e["page"] for e in findings[0]["evidence"]] == [1, 2]
    wrong = doc("CPSE7.txt", "CPSE.7 EPC for the commercial premises to footer", "Other text. follow.")
    assert extract_property_evidence([wrong]) == []


def test_water_incomplete_replies_do_not_establish_absent_services():
    document = doc("Water.txt", "CommercialDW Drainage & Water Enquiry", "2.1 Does foul water from the property drain to a public sewer? The enquiry appears to relate to a plot of land or a recently built property.", "3.1 Is the property connected to mains water supply? The enquiry appears to relate to a plot of land or a recently built property.")
    finding, = extract_property_evidence([document])
    assert "rather than confirming" in finding["found"]
    assert "not proof either" in finding["meaning"]
    affirmative = doc("Water.txt", "CommercialDW Drainage & Water Enquiry 3.1 Is the property connected to mains water supply? Yes. The following is guidance for a plot of land or a recently built property.")
    assert extract_property_evidence([affirmative]) == []


def test_detached_reserve_table_amount_is_not_assigned_or_added_as_a_cost():
    document = doc("Service charge.txt", "Reserve fund. Service charge collected. Column one unrelated fee\n250\n123.45\n-21.34")
    finding, = extract_property_evidence([document])
    assert finding["requires_visual_review"]
    assert "21.34" not in finding["found"]
    assert "not an established buyer liability" in finding["meaning"]
    assert "impact" not in finding


def test_every_quote_is_verbatim_normalised_source_with_hash_and_page():
    document = doc("CPSE2.txt", "CPSE.2 No current outstanding rent arrears. Buyer to rely on documentation provided.")
    for finding in extract_property_evidence([document]):
        for evidence in finding["evidence"]:
            assert evidence["excerpt"] in " ".join(document.text.split())
            assert evidence["document_sha256"] == document.sha256
            assert evidence["page"] == 1
