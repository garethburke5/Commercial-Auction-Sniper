from __future__ import annotations


def page_size_value(choice, total):
    """Resolve the UI page-size choice to a safe integer size."""
    total = max(0, int(total or 0))
    if str(choice).strip().lower() == "all":
        return max(1, total)
    try:
        size = int(choice)
    except (TypeError, ValueError):
        size = 50
    return max(1, size)


def page_count(total, page_size):
    total = max(0, int(total or 0))
    page_size = max(1, int(page_size or 1))
    return max(1, (total + page_size - 1) // page_size)


def clamp_page(page, total, page_size):
    pages = page_count(total, page_size)
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    return min(max(1, page), pages)


def slice_bounds(total, page_size, page):
    total = max(0, int(total or 0))
    page_size = max(1, int(page_size or 1))
    page = clamp_page(page, total, page_size)
    start = min(total, (page - 1) * page_size)
    end = min(total, start + page_size)
    return start, end


def page_window(current, total_pages, max_buttons=7):
    """Return a compact consecutive page-number window centred where practical."""
    total_pages = max(1, int(total_pages or 1))
    max_buttons = max(1, int(max_buttons or 1))
    current = min(max(1, int(current or 1)), total_pages)
    if total_pages <= max_buttons:
        return list(range(1, total_pages + 1))
    half = max_buttons // 2
    start = max(1, current - half)
    end = start + max_buttons - 1
    if end > total_pages:
        end = total_pages
        start = end - max_buttons + 1
    return list(range(start, end + 1))
