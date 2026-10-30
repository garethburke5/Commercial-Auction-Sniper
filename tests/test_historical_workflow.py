from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "historical-lot-corpus.yml"
).read_text()


def test_canonical_appearance_repairs_trigger_a_checkpoint_rebuild():
    push_paths = WORKFLOW[WORKFLOW.index("  push:"):WORKFLOW.index("concurrency:")]
    assert "- data/auction_history/appearances/**" in push_paths


def test_queued_collection_moves_to_current_main_before_collection():
    checkout = WORKFLOW.index("- uses: actions/checkout@v4")
    refresh = WORKFLOW.index("- name: Move queued collection to current main")
    setup = WORKFLOW.index("- uses: actions/setup-python@v5")
    assert checkout < refresh < setup
    assert "github.event_name == 'schedule' || github.event_name == 'push'" in WORKFLOW[refresh:setup]
    assert "git checkout --detach origin/main" in WORKFLOW[refresh:setup]


def test_focused_auction_house_online_6_october_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 6 October 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-10-06 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 6 October 2026" in block


def test_focused_auction_house_online_2_september_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 2 September 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-09-02 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 2 September 2026" in block


def test_focused_auction_house_online_16_december_2025_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 16 December 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-12-16 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 16 December 2025" in block


def test_focused_auction_house_online_9_december_2025_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 9 December 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-12-09 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 9 December 2025" in block


def test_focused_auction_house_online_2_december_2025_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 2 December 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-12-02 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 2 December 2025" in block


def test_focused_auction_house_online_18_november_2025_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 18 November 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-11-18 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 18 November 2025" in block


def test_focused_auction_house_online_28_october_2025_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 28 October 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-10-28 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 28 October 2025" in block


def test_focused_auction_house_online_21_october_2025_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 21 October 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-10-21 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 21 October 2025" in block


def test_focused_auction_house_online_14_october_2025_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 14 October 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-10-14 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 14 October 2025" in block


def test_focused_auction_house_online_7_october_2025_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 7 October 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-10-07 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 7 October 2025" in block


def test_focused_auction_house_online_9_september_2025_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 9 September 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-09-09 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 9 September 2025" in block


def test_focused_auction_house_online_23_september_2025_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 23 September 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-09-23 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 23 September 2025" in block


def test_focused_auction_house_online_16_september_2025_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 16 September 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-09-16 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 16 September 2025" in block


def test_focused_auction_house_online_2_september_2025_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 2 September 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-09-02 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 2 September 2025" in block


def test_focused_auction_house_online_26_august_2025_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 26 August 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-08-26 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 26 August 2025" in block


def test_focused_auction_house_online_12_august_2025_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 12 August 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-08-12 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 12 August 2025" in block


def test_focused_auction_house_online_5_august_2025_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 5 August 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-08-05 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 5 August 2025" in block


def test_focused_auction_house_online_4_november_2025_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 4 November 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-11-04 --workers 16" in block
    assert "Rebuild historical database from banked records and collect Auction House Online 4 November 2025" in block


def test_focused_cottons_repair_skips_broad_rotation():
    focused = WORKFLOW.index("- name: Run focused Cottons split-row recovery")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    assert "scripts/harvest_cottons_results.py" in WORKFLOW[focused:bounded]
    assert "scripts/enrich_cottons_guides.py" in WORKFLOW[focused:bounded]
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Cottons repair" in bounded_condition


def test_normal_cottons_guide_window_clears_bounded_retry_backlog():
    start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    end = WORKFLOW.index("- name: Run focused Cottons split-row recovery", start)
    assert "scripts/enrich_cottons_guides.py 16" in WORKFLOW[start:end]


def test_focused_edward_mellor_pdf_repair_refreshes_all_saved_sheets():
    focused = WORKFLOW.index("- name: Run focused Edward Mellor overlaid-PDF repair")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    assert "scripts/harvest_edward_mellor_pdfs.py 64" in WORKFLOW[focused:bounded]
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Edward Mellor PDF repair" in bounded_condition


def test_source_checkpoint_bundle_precedes_rebase_and_is_artifacted():
    bundle = WORKFLOW.index('git bundle create "$checkpoint_bundle"')
    rebase = WORKFLOW.index("git rebase --autostash origin/main", bundle)
    branch_push = WORKFLOW.index('push origin "HEAD:refs/heads/$checkpoint_branch"', rebase)
    assert bundle < rebase < branch_push
    assert 'git bundle verify "$checkpoint_bundle"' in WORKFLOW
    assert "${{ runner.temp }}/historical-source-checkpoint-*.bundle" in WORKFLOW


def test_bundle_fallback_does_not_block_main_publication():
    assert '\n          test "$checkpoint_saved" = true\n' not in WORKFLOW
    assert 'if test "$checkpoint_saved" = true; then' in WORKFLOW
    assert "the full data commit remains in $checkpoint_bundle" in WORKFLOW


def test_focused_pugh_repair_skips_broad_rotation():
    focused = WORKFLOW.index("- name: Run focused Pugh hybrid archive repair")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    assert "scripts/harvest_pugh_canonical.py" in WORKFLOW[focused:bounded]
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Pugh repair" in bounded_condition


def test_focused_clive_emson_legacy_expansion_skips_broad_rotation():
    focused = WORKFLOW.index("- name: Run focused Clive Emson article-linked legacy expansion")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_clive_emson_canonical.py --roundups" in block
    assert "scripts/harvest_clive_emson_canonical.py --all-incomplete" not in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Clive Emson legacy expansion" in bounded_condition


def test_focused_clarke_simpson_expansion_skips_broad_rotation():
    focused = WORKFLOW.index("- name: Collect Clarke & Simpson complete property archive")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py clarke-simpson --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Clarke and Simpson archive expansion" in bounded_condition


def test_focused_higgins_drysdale_expansion_skips_broad_rotation():
    focused = WORKFLOW.index("- name: Collect Higgins Drysdale complete property archive")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py higgins-drysdale --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Higgins Drysdale archive expansion" in bounded_condition


def test_focused_brown_co_expansion_skips_broad_rotation():
    focused = WORKFLOW.index("- name: Collect Brown and Co complete property archive")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py brown-co --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Brown and Co archive expansion" in bounded_condition


def test_focused_property_auction_house_expansion_skips_broad_rotation():
    focused = WORKFLOW.index("- name: Collect The Property Auction House complete property archive")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py the-property-auction-house --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused The Property Auction House archive expansion" in bounded_condition


def test_focused_property_auction_agent_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Property Auction Agent complete property archive")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py property-auction-agent --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Property Auction Agent archive expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Property Auction Agent archive expansion" in WORKFLOW[guide_start:guide_end]


def test_focused_lot9_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect LOT9 Auction House complete property archive")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py lot9-auction-house --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused LOT9 Auction House archive expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused LOT9 Auction House archive expansion" in WORKFLOW[guide_start:guide_end]


def test_focused_auction_north_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction North complete property archive")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-north --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction North archive expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction North archive expansion" in WORKFLOW[guide_start:guide_end]


def test_focused_sage_co_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Sage and Co complete property archive")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py sage-co-auctions --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Sage and Co archive expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Sage and Co archive expansion" in WORKFLOW[guide_start:guide_end]


def test_focused_bowen_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Bowen complete property archive")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py bowen --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Bowen archive expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Bowen archive expansion" in WORKFLOW[guide_start:guide_end]


def test_focused_astleys_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Astleys complete property archive")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py astleys --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Astleys archive expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Astleys archive expansion" in WORKFLOW[guide_start:guide_end]


def test_focused_loveitts_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Loveitts retained first-party event archive")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_loveitts_archive.py --workers 20" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Loveitts archive expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Loveitts archive expansion" in WORKFLOW[guide_start:guide_end]


def test_focused_butters_john_bee_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Butters John Bee paired catalogue and result archive")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_butters_john_bee_archive.py --workers 12" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Butters John Bee archive expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Butters John Bee archive expansion" in WORKFLOW[guide_start:guide_end]


def test_focused_purplebricks_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Purplebricks complete retained property archive")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_purplebricks_online_auctions.py" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Purplebricks archive expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Purplebricks archive expansion" in WORKFLOW[guide_start:guide_end]


def test_focused_symonds_sampson_repair_skips_broad_rotation():
    focused = WORKFLOW.index("- name: Run focused Symonds and Sampson reconciliation repair")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    assert "scripts/harvest_symonds_sampson_canonical.py --reconcile-saved-state" in WORKFLOW[focused:bounded]
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Symonds and Sampson repair" in bounded_condition


def test_focused_online_result_state_repair_skips_broad_rotation():
    focused = WORKFLOW.index("- name: Reclassify saved online-result denominator limitations")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    assert "scripts/reconcile_online_result_state_errors.py" in WORKFLOW[focused:bounded]
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused online-result state repair" in bounded_condition



def test_focused_opal_newlands_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Opal and Newlands complete property archives")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py opal-property --workers 16" in block
    assert "scripts/harvest_eig_retained_grids.py newlands-property --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Opal and Newlands archive expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Opal and Newlands archive expansion" in WORKFLOW[guide_start:guide_end]


def test_focused_landmark_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Landmark Auctions complete property archive")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py landmark-auctions --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Landmark Auctions archive expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Landmark Auctions archive expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Landmark Auctions archive expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online November 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-11 --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online archive expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online archive expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online archive expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_october_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online October 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-10 --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online October 2025 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online October 2025 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online October 2025 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_march_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 25 March 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-03-25 --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online March 2025 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online March 2025 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online March 2025 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_april_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 15 April 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-04-15 --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online April 2025 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online April 2025 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online April 2025 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_may_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 27 May 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-05-27 --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online May 2025 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online May 2025 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online May 2025 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_august_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 19 August 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-08-19 --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online August 2025 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online August 2025 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online August 2025 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_november_second_event_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 11 November 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-11-11 --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online November 2025 second-event expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online November 2025 second-event expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online November 2025 second-event expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_july_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 29 July 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-07-29 --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online July 2025 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online July 2025 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online July 2025 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_20_may_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 20 May 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-05-20 --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 20 May 2025 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 20 May 2025 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 20 May 2025 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_24_june_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 24 June 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-06-24 --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 24 June 2025 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 24 June 2025 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 24 June 2025 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_30_september_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 30 September 2025 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2025-09-30 --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 30 September 2025 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 30 September 2025 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 30 September 2025 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_13_january_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 13 January 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-01-13 --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 13 January 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 13 January 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 13 January 2026 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_30_june_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 30 June 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-06-30 --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 30 June 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 30 June 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 30 June 2026 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_31_march_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 31 March 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-03-31 --workers 16" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 31 March 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 31 March 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 31 March 2026 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_14_april_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 14 April 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-04-14 --workers 16" in block
    assert "Run focused Auction House Online 14 April 2026 expansion" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online archive expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online archive expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online archive expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_24_february_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 24 February 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-02-24 --workers 16" in block
    assert "Run focused Auction House Online 24 February 2026 expansion" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 24 February 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 24 February 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 24 February 2026 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_17_march_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 17 March 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-03-17 --workers 16" in block
    assert "Run focused Auction House Online 17 March 2026 expansion" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 17 March 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 17 March 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 17 March 2026 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_24_march_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 24 March 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-03-24 --workers 16" in block
    assert "Run focused Auction House Online 24 March 2026 expansion" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 24 March 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 24 March 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 24 March 2026 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_21_april_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 21 April 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-04-21 --workers 16" in block
    assert "Run focused Auction House Online 21 April 2026 expansion" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 21 April 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 21 April 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 21 April 2026 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_28_april_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 28 April 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-04-28 --workers 16" in block
    assert "Run focused Auction House Online 28 April 2026 expansion" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 28 April 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 28 April 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 28 April 2026 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_9_june_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 9 June 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-06-09 --workers 16" in block
    assert "Run focused Auction House Online 9 June 2026 expansion" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 9 June 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 9 June 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 9 June 2026 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_26_may_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 26 May 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-05-26 --workers 16" in block
    assert "Run focused Auction House Online 26 May 2026 expansion" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 26 May 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 26 May 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 26 May 2026 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_2_june_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 2 June 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-06-02 --workers 16" in block
    assert "Run focused Auction House Online 2 June 2026 expansion" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 2 June 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 2 June 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 2 June 2026 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_16_june_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 16 June 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-06-16 --workers 16" in block
    assert "Run focused Auction House Online 16 June 2026 expansion" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 16 June 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 16 June 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 16 June 2026 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_23_june_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 23 June 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-06-23 --workers 16" in block
    assert "Run focused Auction House Online 23 June 2026 expansion" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 23 June 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 23 June 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 23 June 2026 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_7_july_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 7 July 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-07-07 --workers 16" in block
    assert "Run focused Auction House Online 7 July 2026 expansion" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 7 July 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 7 July 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 7 July 2026 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_14_july_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 14 July 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-07-14 --workers 16" in block
    assert "Run focused Auction House Online 14 July 2026 expansion" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 14 July 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 14 July 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 14 July 2026 expansion" in WORKFLOW[ocr_start:ocr_end]


def test_focused_auction_house_online_21_july_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 21 July 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-07-21 --workers 16" in block
    assert "Run focused Auction House Online 21 July 2026 expansion" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 21 July 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 21 July 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 21 July 2026 expansion" in WORKFLOW[ocr_start:ocr_end]

def test_focused_auction_house_online_28_july_expansion_is_isolated():
    focused = WORKFLOW.index("- name: Collect Auction House Online 28 July 2026 shared-platform event")
    bounded = WORKFLOW.index("- name: Resume bounded archive batch")
    assert focused < bounded
    block = WORKFLOW[focused:bounded]
    assert "scripts/harvest_eig_retained_grids.py auction-house-online-2026-07-28 --workers 16" in block
    assert "Run focused Auction House Online 28 July 2026 expansion" in block
    bounded_condition = WORKFLOW[bounded:WORKFLOW.index("- name:", bounded + 10)]
    assert "Run focused Auction House Online 28 July 2026 expansion" in bounded_condition
    guide_start = WORKFLOW.index("- name: Enrich banked Cottons appearances with exact catalogue guides")
    guide_end = WORKFLOW.index("- name:", guide_start + 10)
    assert "Run focused Auction House Online 28 July 2026 expansion" in WORKFLOW[guide_start:guide_end]
    ocr_start = WORKFLOW.index("- name: Ensure PDF and OCR extraction is available")
    ocr_end = WORKFLOW.index("- name:", ocr_start + 10)
    assert "Run focused Auction House Online 28 July 2026 expansion" in WORKFLOW[ocr_start:ocr_end]

