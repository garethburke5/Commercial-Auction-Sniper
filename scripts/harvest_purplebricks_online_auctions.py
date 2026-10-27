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
    )
    harvest()
