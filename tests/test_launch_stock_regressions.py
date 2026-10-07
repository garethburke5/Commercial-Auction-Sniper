"""Asset evidence, not nearby businesses or agency credits, controls eligibility."""
from collectors.publication_quality import publication_exclusion, commercial_decision


def test_agent_credit_cannot_turn_a_flat_into_a_commercial_investment():
    row = {'description': 'Joint Agent: Entwistle Green Estate Agents A first floor two bedroom apartment benefitting from double glazing, central heating, communal gardens and parking.', 'property_type': 'Mixed Use'}
    assert publication_exclusion(row).startswith('Pure residential')


def test_location_without_colon_cannot_turn_bare_land_into_a_supermarket():
    row = {'property_type': 'Retail', 'description': 'Comprising a row of 4 adjacent parcels of freehold land. Buyers are to obtain all necessary permissions. Location Directly facing the road between the large Sainsburys Supermarket and Petrol Station. Tenure - Freehold'}
    assert publication_exclusion(row).startswith('Unverified commercial use')


def test_real_commercial_asset_evidence_survives_location_filter():
    for text in ('A hairdressing salon with two self contained flats. Location The property fronts the High Street.',
                 'A parcel of land including a haulage yard with a storage building.',
                 'INDUSTRIAL DEVELOPMENT OPPORTUNITY. Vacant parcel of land.',
                 'Popular Location Situated in Southampton, a building with commercial space and flats.',
                 'Joint Agent: Example Estate Agents A ground floor shop with a flat above.'):
        assert commercial_decision({'description': text}) is True


def test_source_lots_without_current_scope_cannot_be_a_silent_healthy_zero():
    from source_reconciliation import reconcile
    h = {'source': 'Test Source', 'status': 'LIVE', 'reconciliation': {'source_lot_count': 4, 'lots_parsed': 4, 'commercial_mixed_candidates': 0}}
    record = next(r for r in reconcile({'properties': [], 'source_health': [h]})['sources'] if r['auctioneer'] == 'Test Source')
    assert record['status'] == 'DEGRADED'
    assert 'currency' in record['failure_reason']


def test_shop_income_and_flat_ground_rents_are_not_a_pure_ground_rent_investment():
    from property_summary import _is_ground_rent_investment
    assert not _is_ground_rent_investment({}, 'grade ii listed freehold retail units and residential ground rent investment', False)
