"""Production entry point with lifecycle-safe Auction House collectors.

Keeps run_collectors.py as the canonical snapshot/quality pipeline while replacing
Auction House London and regional collector functions with lifecycle-safe versions.
"""
from __future__ import annotations

import run_collectors as pipeline
from collectors import auction_house_regions_resilient as regional
from collectors import auction_house_london_resilient as london


_REPLACEMENTS = {
    "collect_east_anglia": regional.collect_east_anglia,
    "collect_west_yorkshire": regional.collect_west_yorkshire,
    "collect_sussex_hampshire": regional.collect_sussex_hampshire,
    "collect_south_west": regional.collect_south_west,
    "collect_wales": regional.collect_wales,
    "collect_cumbria": regional.collect_cumbria,
    "collect_north_east": regional.collect_north_east,
    "collect_north_west": regional.collect_north_west,
    "collect_lincolnshire": regional.collect_lincolnshire,
    "collect_manchester": regional.collect_manchester,
    "collect_chesterfield": regional.collect_chesterfield,
    "collect_coventry_warwickshire": regional.collect_coventry_warwickshire,
    "collect_scotland": regional.collect_scotland,
    "collect_hull_east_yorkshire": regional.collect_hull_east_yorkshire,
    "collect_birmingham_black_country": regional.collect_birmingham_black_country,
    "collect_northants_beds_bucks": regional.collect_northants_beds_bucks,
    "collect_beds_bucks": regional.collect_beds_bucks,
    "collect_leicestershire": regional.collect_leicestershire,
    "collect_tees_valley": regional.collect_tees_valley,
    "collect_national_online": regional.collect_national_online,
}


def _install_replacements():
    upgraded = []
    for collector in pipeline.COLLECTORS:
        module = getattr(collector, "__module__", "")
        name = getattr(collector, "__name__", "")
        if module == "collectors.auction_house_regions":
            upgraded.append(_REPLACEMENTS.get(name, collector))
        elif module == "collectors.auction_house_london_v2" and name == "collect":
            upgraded.append(london.collect)
        else:
            upgraded.append(collector)
    pipeline.COLLECTORS = upgraded


def run():
    _install_replacements()
    pipeline.run()


if __name__ == "__main__":
    run()
