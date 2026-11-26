"""Bank CPN Auctions' complete public first-party search/result grid.

CPN's trading shorthand is an alias of the same auctioneer, not a separate
operator. The shared EIG runner reconciles stable lot identities globally,
snapshots every grid page and, for this source, enriches missing labelled
guide and rent evidence from each individual first-party lot detail page.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import harvest_harman_healy_results as shared


BASE = "https://auctions.thecpn.co.uk"
AUCTIONEER = "CPN Auctions"
SLUG = "cpn-auctions"


def configure_cpn() -> None:
    shared.configure(
        BASE,
        AUCTIONEER,
        SLUG,
        archive_path="/search",
        operator_metadata={
            "trading_name_aliases": ["CPN"],
            "trading_name_aliases_counted_separately": False,
            "operator_scope_note": (
                "CPN is a trading shorthand for CPN Auctions and is not "
                "counted as a separate auctioneer."
            ),
        },
        enrich_details=True,
    )


def main() -> None:
    configure_cpn()
    shared.harvest()


if __name__ == "__main__":
    main()
