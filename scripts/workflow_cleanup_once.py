from pathlib import Path
import re

wf = Path('.github/workflows')

# Keep only durable production/manual workflows. Remove one-off mutation,
# diagnostic, hotfix and source-specific repair workflows that cause fan-out.
keep = {
    'auction-sniper-scan.yml',
    'auction-sniper-publish-now.yml',
    'historical-backfill.yml',
    'legal-pack-engine-tests.yml',
    'workflow-cleanup-once.yml',
}

prefixes = (
    'apply-', 'diagnose-', 'fix-', 'hotfix-', 'inspect-', 'trace-', 'verify-',
    'restore-', 'remove-', 'replace-', 'tidy-', 'enrich-', 'externalise-',
    'measure-', 'move-', 'lazy-load-', 'build-complete-', 'test-progressive-',
    'savills-',
)
exact = {
    'add-light-background-toggle.yml',
    'allsop-image-diagnostic.yml',
    'strettons-durable-repair.yml',
    'symonds-image-diagnostic.yml',
}
removed=[]
for p in sorted(wf.glob('*.yml')):
    if p.name in keep:
        continue
    if p.name in exact or p.name.startswith(prefixes):
        p.unlink()
        removed.append(p.name)

# Historical work is deliberate/manual only and has its own concurrency group.
hist = wf / 'historical-backfill.yml'
text = hist.read_text(encoding='utf-8')
text = re.sub(
    r'(?ms)^on:\n.*?^permissions:',
    'on:\n  workflow_dispatch:\n\npermissions:',
    text,
    count=1,
)
text = text.replace('group: auction-sniper-production-scan', 'group: auction-sniper-history-backfill')
hist.write_text(text, encoding='utf-8')

# Production CI must run when the board itself or pagination logic changes.
scan = wf / 'auction-sniper-scan.yml'
text = scan.read_text(encoding='utf-8')
needle = "      - 'app.py'\n"
replacement = "      - 'app.py'\n      - 'legacy_app.py'\n      - 'pagination.py'\n"
if "      - 'legacy_app.py'\n" not in text:
    if needle not in text:
        raise SystemExit('production path anchor missing')
    text = text.replace(needle, replacement, 1)
scan.write_text(text, encoding='utf-8')

print('REMOVED', len(removed))
for name in removed:
    print(name)
