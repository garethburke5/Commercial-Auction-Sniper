from pathlib import Path

# 1) Clive Emson: recognise explicit "Currently part let at £... per annum".
p = Path('collectors/clive_emson.py')
s = p.read_text(encoding='utf-8')
old = r'r"\bCurrently\s+let\s+at\s+(£\s*[\d,]+(?:\.\d{1,2})?)\s*(?:per annum|p\.?a\.?|pa)\b",'
new = r'r"\bCurrently\s+(?:part\s+)?let\s+at\s+(£\s*[\d,]+(?:\.\d{1,2})?)\s*(?:per annum|p\.?a\.?|pa)\b",'
if old not in s:
    raise SystemExit('Clive rent anchor missing')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')

# 2) Property summaries: generic part-let/vacancy title + ERV/asset-management facts.
p = Path('property_summary.py')
s = p.read_text(encoding='utf-8')
old = '''    if kind == "OFFICE" and rent and part_vacant:\n        return "PART-LET OFFICE INVESTMENT + VACANCY"\n'''
new = '''    if rent and part_vacant:\n        return f"PART-LET {kind} INVESTMENT + VACANCY"\n'''
if old not in s:
    raise SystemExit('part-vacant title anchor missing')
s = s.replace(old, new, 1)

anchor = '''def _lease_highlight(row, text):\n'''
insert = '''def _rental_value_highlights(text):\n    out = []\n    m = re.search(r"Estimated Rental Value\\s*(?:is|of|:)?\\s*£\\s*([\\d,]+)(?:\\.\\d{1,2})?\\s*(?:per annum|p\\.?a\\.?|pa)", text, re.I)\n    if m:\n        out.append(f"ERV £{int(m.group(1).replace(',', '')):,} p.a.")\n    m = re.search(r"vacant ground floor[^.]{0,140}?estimated rental value of\\s*£\\s*([\\d,]+)(?:\\.\\d{1,2})?\\s*(?:per annum|p\\.?a\\.?|pa)", text, re.I)\n    if m:\n        out.append(f"Vacant ground floor ERV £{int(m.group(1).replace(',', '')):,} p.a.")\n    return out\n\n\ndef _asset_management_highlight(low):\n    if "asset management potential" in low or any(x in low for x in ("re-letting", "reletting", "subdivision", "owner occupation")):\n        actions=[]\n        if "re-let" in low or "re-letting" in low or "reletting" in low:\n            actions.append("re-let")\n        if "subdivision" in low or "subdivide" in low:\n            actions.append("subdivide")\n        if "owner occupation" in low or "owner-occupation" in low:\n            actions.append("owner-occupy")\n        return "Asset management" + (": " + " / ".join(dict.fromkeys(actions)) if actions else " potential")\n    return None\n\n\ndef _epc_highlight(text, low):\n    if "epc rating" not in low:\n        return None\n    ratings=[]\n    for grade, score in re.findall(r"\\b([A-G])\\s*\\(\\s*(\\d{1,3})\\s*\\)", text, re.I):\n        token=f"{grade.upper()} ({int(score)})"\n        if token not in ratings:\n            ratings.append(token)\n    return "EPC " + " · ".join(ratings[:3]) if ratings else None\n\n\n'''
if anchor not in s:
    raise SystemExit('summary helper anchor missing')
s = s.replace(anchor, insert + anchor, 1)

old = '''    area = _extract_area(row, text)\n    if area:\n        highlights.append(area)\n\n    vacancy = re.search'''
new = '''    area = _extract_area(row, text)\n    if area:\n        highlights.append(area)\n\n    # Surface the commercial decision facts that generic cards otherwise hide.\n    highlights.extend(_rental_value_highlights(text))\n    asset_management = _asset_management_highlight(low)\n    if asset_management:\n        highlights.append(asset_management)\n    if "co-op/somerfield" in low or ("somerfield" in low and "argos" in low):\n        highlights.append("Former Co-op/Somerfield + Argos accommodation")\n    epc = _epc_highlight(text, low)\n    if epc:\n        highlights.append(epc)\n\n    vacancy = re.search'''
if old not in s:
    raise SystemExit('summary insertion anchor missing')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')

# 3) Regression tests for the Truro example supplied by the user and negative VAT semantics.
Path('tests/test_clive_emson_truro_regression.py').write_text('''import unittest\n\nfrom collectors.clive_emson import _parse_occupation, _parse_passing_rent\nfrom property_summary import build_opportunity_summary\n\n\nTEXT = """\nLot 29 Substantial City Centre Freehold Commercial Building With Income And Asset Management Potential.\nGUIDE PRICE £200,000+ FEES. Currently part let at £21,000 per annum. Estimated Rental Value £71,000 per annum.\nCommercial Investment. Freehold. Extensive vacant accommodation offering scope for re-letting, subdivision or owner occupation.\nFormer Co-op/Somerfield and Argos areas providing generous and flexible commercial space.\nPart of the building is let to a dance studio with the lease expiring November 2030 at a current rental of £15,000 per annum\nand there is a barber's let at a current rental of £6,000 per annum, also expiring November 2030, and with a break in 2028.\nIt is considered the vacant ground floor level has an estimated rental value of £50,000 per annum.\nEPC Ratings C (71). Total Floor Area 1,739 sq.m. B (49). Total Floor Area 76 sq.m. E (122). Total Floor Area 338 sq.m.\nFreehold with Part Vacant Possession.\n"""\n\n\nclass TruroRegressionTests(unittest.TestCase):\n    def test_part_let_total_passing_rent_wins(self):\n        self.assertEqual(_parse_passing_rent(TEXT, guide_price=200000), 21000)\n        self.assertEqual(_parse_occupation(TEXT), "Part Vacant / Part Let")\n\n    def test_summary_surfaces_asset_management_and_erv(self):\n        row = {\n            "property_type": "Commercial Investment",\n            "occupation": "Part Vacant / Part Let",\n            "annual_rent": 21000,\n            "description": TEXT,\n        }\n        title, highlights = build_opportunity_summary(row)\n        self.assertEqual(title, "PART-LET COMMERCIAL INVESTMENT + VACANCY")\n        joined = " | ".join(highlights)\n        self.assertIn("ERV £71,000 p.a.", joined)\n        self.assertIn("Asset management", joined)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''', encoding='utf-8')

Path('tests/test_acuitus_vat_negative.py').write_text('''import unittest\nfrom collectors.core import parse_vat\n\nclass AcuitusVatNegativeTests(unittest.TestCase):\n    def test_not_elected_for_vat_is_not_applicable(self):\n        self.assertEqual(parse_vat("The property is Not Elected for VAT"), "NOT APPLICABLE")\n\nif __name__ == "__main__":\n    unittest.main()\n''', encoding='utf-8')

print('data regressions applied')
