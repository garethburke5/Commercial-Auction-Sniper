import history_v2


def test_exact_history_match(monkeypatch):
    monkeypatch.setattr(history_v2, 'load_index', lambda: {
        'by_postcode': {
            'SA311QL': [{
                'event_id': 'e1',
                'property_id': 'p1',
                'address': '8 Red Street, Carmarthen, SA31 1QL',
                'auction_date': '2019-01-01',
                'source': 'Allsop Commercial',
            }]
        }
    })
    matches = history_v2.find_history('8 Red Street, Carmarthen, Dyfed, SA31 1QL')
    assert len(matches) == 1
    assert matches[0]['match_level'] in ('EXACT', 'HIGH', 'PROBABLE')


def test_neighbour_same_postcode_does_not_auto_match(monkeypatch):
    monkeypatch.setattr(history_v2, 'load_index', lambda: {
        'by_postcode': {
            'SA311QL': [{
                'event_id': 'e2',
                'property_id': 'p2',
                'address': '15 Red Street, Carmarthen, SA31 1QL',
                'auction_date': '2019-01-01',
                'source': 'Allsop Commercial',
            }]
        }
    })
    matches = history_v2.find_history('8 Red Street, Carmarthen, SA31 1QL')
    assert matches == []
    possible = history_v2.find_history('8 Red Street, Carmarthen, SA31 1QL', include_possible=True)
    assert possible and possible[0]['match_level'] == 'POSSIBLE_RELATED'


def test_google_fallback_when_no_internal_history(monkeypatch):
    monkeypatch.setattr(history_v2, 'find_history', lambda address, include_possible=False, limit=20: [])
    action = history_v2.history_action('2-7 Market Way, Scarborough YO11 1HR')
    assert action['internal'] is False
    assert 'google.com/search' in action['url']


def test_internal_history_route_when_match_exists(monkeypatch):
    monkeypatch.setattr(history_v2, 'find_history', lambda address, include_possible=False, limit=20: [{'event_id': 'e1'}])
    action = history_v2.history_action('8 Red Street, Carmarthen SA31 1QL')
    assert action['internal'] is True
    assert action['count'] == 1
    assert action['url'].startswith('/History?address=')
