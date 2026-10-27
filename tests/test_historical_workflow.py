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
