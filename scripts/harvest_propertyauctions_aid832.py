#!/usr/bin/env python3
"""Compatibility entry point for the retained Allsop AID 832 grid."""

import json

from scripts.harvest_propertyauctions_allsop_results import SPECS, capture, money, parse_result


if __name__ == "__main__":
    result = capture(SPECS[832])
    print(json.dumps({
        "source": result["archive_url"],
        "auction_date": result["auction_date"],
        "published_rows": result["published_grid_rows"],
        "offered": result["published_offered_count"],
        "catalogue_complete": result["catalogue_complete"],
    }))
