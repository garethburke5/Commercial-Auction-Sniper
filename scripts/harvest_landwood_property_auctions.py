"""Bank Landwood Property Auctions' complete public EIG past-lots archive."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.harvest_harman_healy_results import configure, harvest


if __name__ == "__main__":
    configure(
        "https://www.landwoodpropertyauctions.com",
        "Landwood Property Auctions",
        "landwood-property-auctions",
    )
    harvest()
