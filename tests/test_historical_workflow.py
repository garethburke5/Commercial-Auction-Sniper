from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "historical-lot-corpus.yml"
).read_text()


def test_queued_schedule_moves_to_current_main_before_collection():
    checkout = WORKFLOW.index("- uses: actions/checkout@v4")
    refresh = WORKFLOW.index("- name: Move queued schedule to current main")
    setup = WORKFLOW.index("- uses: actions/setup-python@v5")
    assert checkout < refresh < setup
    assert "if: github.event_name == 'schedule'" in WORKFLOW[refresh:setup]
    assert "git checkout --detach origin/main" in WORKFLOW[refresh:setup]


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
