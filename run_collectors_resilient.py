"""Production entry point with lifecycle-safe Auction House regional collectors.

Keeps run_collectors.py as the canonical snapshot/quality pipeline while replacing
only the Auction House regional collector functions with the lifecycle-safe version.
"""
from __future__ import annotations

import run_collectors as pipeline
from collectors import auction_house_regions_resilient as resilient


_REPLACEMENTS = {
    "collect_east_anglia": resilient.collect_east_anglia,
    "collect_west_yorkshire": resilient.collect_west_yorkshire,
    "collect_sussex_hampshire": resilient.collect_sussex_hampshire,
    "collect_south_west": resilient.collect_south_west,
    "collect_wales": resilient.collect_wales,
    "collect_cumbria": resilient.collect_cumbria,
    "collect_north_east": resilient.collect_north_east,
    "collect_north_west": resilient.collect_north_west,
    "collect_lincolnshire": resilient.collect_lincolnshire,
    "collect_manchester": resilient.collect_manchester,
    "collect_chesterfield": resilient.collect_chesterfield,
    "collect_coventry_warwickshire": resilient.collect_coventry_warwickshire,
    "collect_scotland": resilient.collect_scotland,
    "collect_hull_east_yorkshire": resilient.collect_hull_east_yorkshire,
    "collect_birmingham_black_country": resilient.collect_birmingham_black_country,
    "collect_northants_beds_bucks": resilient.collect_northants_beds_bucks,
    "collect_beds_bucks": resilient.collect_beds_bucks,
    "collect_leicestershire": resilient.collect_leicestershire,
    "collect_tees_valley": resilient.collect_tees_valley,
    "collect_national_online": resilient.collect_national_online,
}


def _install_replacements():
    upgraded = []
    for collector in pipeline.COLLECTORS:
        if getattr(collector, "__module__", "") == "collectors.auction_house_regions":
            upgraded.append(_REPLACEMENTS.get(getattr(collector, "__name__", ""), collector))
        else:
            upgraded.append(collector)
    pipeline.COLLECTORS = upgraded


def run():
    _install_replacements()
    pipeline.run()


if __name__ == "__main__":
    run()
