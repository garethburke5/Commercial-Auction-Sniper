"""Public plan presentation and server-owned feature entitlements.

Stripe Price IDs remain deployment configuration. Match those prices to this
catalogue before enabling checkout; report allowances are deliberately unset.
"""
import json
from pathlib import Path

CATALOGUE = json.loads(Path(__file__).with_name('plan_catalogue.json').read_text())
FREE = frozenset({'save'})
INVESTOR = FREE | {'watch', 'saved_searches', 'alerts', 'notes', 'bid_targets', 'intelligence'}
PROFESSIONAL = INVESTOR | {'reports', 'export'}
ENTITLEMENTS = {'free': FREE, 'investor': INVESTOR,
                'professional': PROFESSIONAL, 'business': PROFESSIONAL | {'api'}}
