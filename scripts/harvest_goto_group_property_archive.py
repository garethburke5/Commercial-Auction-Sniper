"""Bank the public GOTO Group aggregate retained property archive.

The aggregate index exposes stable lot UUIDs across GOTO's branded and partner
channels.  UUIDs already banked by a channel collector are excluded as shared
source evidence, while URL-less deleted cards remain explicit denominator
exclusions rather than receiving synthetic identities.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.harvest_harman_healy_results import configure, harvest


if __name__ == "__main__":
    configure(
        "https://list.gotoproperties.co.uk",
        "GOTO Group",
        "goto-group-property-archive",
        archive_path="/search",
        operator_metadata={
            "operator_legal_name": "Genle Limited",
            "operator_company_number": "09790404",
            "operator_trading_name": "GOTO Group",
            "operator_counting_basis": (
                "GOTO Group is counted once as the operating auction platform; "
                "branded and partner channels in the aggregate archive are not "
                "counted as additional auctioneers"
            ),
        },
        allow_missing_identity_exclusions=True,
    )
    harvest()
