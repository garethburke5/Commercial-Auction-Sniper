from pathlib import Path
import json

CONFIG = Path("config/target_sources.json")


def load_target_sources(path=CONFIG):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return list(data.get("required_sources", [])), list(data.get("expansion_sources", []))


def manifest_coverage(source_health, path=CONFIG):
    required, expansion = load_target_sources(path)
    by_name = {str(x.get("source") or "").strip(): x for x in source_health}
    represented = set(by_name)
    missing_required = [x for x in required if x not in represented]
    missing_expansion = [x for x in expansion if x not in represented]
    unhealthy_required = [
        x for x in required
        if x in by_name and str(by_name[x].get("status") or "").upper() in {"FAILED", "NOT IMPLEMENTED", "MISSING"}
    ]
    return {
        "required_sources": required,
        "expansion_sources": expansion,
        "represented_sources": sorted(represented),
        "missing_required_sources": missing_required,
        "missing_expansion_sources": missing_expansion,
        "unhealthy_required_sources": unhealthy_required,
        "required_coverage_pct": round(100 * (len(required) - len(missing_required)) / len(required), 1) if required else 100.0,
        "acceptance_ready": not missing_required and not unhealthy_required,
    }


def append_missing_health(source_health, path=CONFIG):
    coverage = manifest_coverage(source_health, path)
    for source in coverage["missing_required_sources"]:
        source_health.append({
            "source": source,
            "status": "NOT IMPLEMENTED",
            "lots_seen": 0,
            "expected_count": None,
            "discovered_count": None,
            "coverage_pct": None,
            "authoritative_snapshot": False,
            "scope_dates": [],
            "message": "Required target source has no production collector. Acceptance is blocked until it is assessed and implemented or explicitly classified as catalogue-pending by a collector.",
            "checked_at": None,
        })
    return manifest_coverage(source_health, path)
