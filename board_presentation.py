"""Catalogue visibility and availability are distinct concepts."""
from datetime import date, datetime, timezone

UNAVAILABLE = {'SOLD', 'SOLD PRIOR', 'WITHDRAWN', 'WITHDRAWN PRIOR', 'POSTPONED'}


def catalogue_status(row):
    status = str(row.get('status') or '').strip().upper().replace('_', ' ')
    return status if status in UNAVAILABLE else None


def withdrawn_row(row):
    return catalogue_status(row) in {'WITHDRAWN', 'WITHDRAWN PRIOR'}


def searchable_catalogue_row(row, *, in_current_catalogue=True, today=None):
    """Withdrawal changes availability, never the ability to find a captured lot."""
    return withdrawn_row(row) or (in_current_catalogue and current_board_row(row, today))


def verified_post_auction_available(row, now=None):
    """A past auction date is not a sale result; require recent exact-lot evidence."""
    if row.get('source') not in {'Allsop Commercial', 'Barnard Marcus'} or catalogue_status(row):
        return False
    if str(row.get('source_availability') or '').upper() not in {'AVAILABLE', 'UNSOLD', 'FOR SALE'}:
        return False
    try:
        checked = datetime.fromisoformat(str(row.get('availability_checked_at') or '').replace('Z', '+00:00'))
        if checked.tzinfo is None:
            return False
        age = ((now or datetime.now(timezone.utc)) - checked).total_seconds()
        return -300 <= age <= 14 * 3600
    except (KeyError, TypeError, ValueError):
        return False


def current_board_row(row, today=None):
    today = today or date.today()
    status = str(row.get('status') or '').strip().upper().replace('_', ' ')
    if status in {'ARCHIVED', 'AUCTION ENDED', 'COMPLETED', 'STALE SOURCE'}:
        return False
    if verified_post_auction_available(row):
        return True
    try:
        return date.fromisoformat(str(row.get('date') or row.get('auction_date') or '')[:10]) >= today
    except ValueError:
        return True


def available_row(row, today=None):
    return current_board_row(row, today) and not catalogue_status(row)
