"""Catalogue visibility and availability are distinct concepts."""
from datetime import date

UNAVAILABLE = {'SOLD', 'SOLD PRIOR', 'WITHDRAWN', 'WITHDRAWN PRIOR', 'POSTPONED'}


def catalogue_status(row):
    status = str(row.get('status') or '').strip().upper().replace('_', ' ')
    return status if status in UNAVAILABLE else None


def current_board_row(row, today=None):
    today = today or date.today()
    status = str(row.get('status') or '').strip().upper().replace('_', ' ')
    if status in {'ARCHIVED', 'AUCTION ENDED', 'COMPLETED', 'STALE SOURCE'}:
        return False
    try:
        return date.fromisoformat(str(row.get('date') or row.get('auction_date') or '')[:10]) >= today
    except ValueError:
        return True


def available_row(row, today=None):
    return current_board_row(row, today) and not catalogue_status(row)
