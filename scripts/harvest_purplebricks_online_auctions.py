"""Bank Purplebricks' complete public GOTO retained property archive."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.harvest_harman_healy_results import configure, harvest


if __name__ == "__main__":
    configure(
        "https://purplebricks.gotoproperties.co.uk",
        "Purplebricks Online Auctions",
        "purplebricks-online-auctions",
        archive_path="/search",
        operator_metadata={
            "operator_legal_name": "Genle Limited",
            "operator_company_number": "09790404",
            "operator_trading_name": "GOTO Group",
            "branded_channel": "Purplebricks Online Auctions",
            "operator_counting_basis": (
                "Purplebricks is the branded auction channel and GOTO Group is "
                "the operating platform; they are one retained corpus source, "
                "not two auctioneers"
            ),
        },
    )
    harvest()
