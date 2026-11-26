"""Bank Brookvale Auctions' complete public first-party search/result grid.

Partner-agent names published inside lot descriptions are provenance, not
separate auctioneers. Stable EIG lot IDs are deduplicated against every other
retained white-label source before any growth is claimed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import harvest_harman_healy_results as shared


BASE = "https://auction.brookvale.uk"
AUCTIONEER = "Brookvale Auctions"
SLUG = "brookvale-auctions"


def configure_brookvale() -> None:
    shared.configure(
        BASE,
        AUCTIONEER,
        SLUG,
        archive_path="/search",
        operator_metadata={
            "partner_agents_not_counted_as_auctioneers": True,
            "operator_scope_note": (
                "Brookvale Auctions is the auctioneer; named partner agents "
                "remain source provenance and are not counted separately."
            ),
        },
    )


def main() -> None:
    configure_brookvale()
    shared.harvest()


if __name__ == "__main__":
    main()
