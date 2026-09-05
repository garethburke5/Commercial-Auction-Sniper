from pathlib import Path
import json

CONFIG = Path("config/target_sources.json")


def _load_config(path=CONFIG):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_target_sources(path=CONFIG):
    data = _load_config(path)
    return list(data.get("required_sources", [])), list(data.get("expansion_sources", []))


def _source_aliases(path=CONFIG):
    data = _load_config(path)
    aliases = data.get("source_aliases", {}) or {}
    return {str(k).strip(): str(v).strip() for k, v in aliases.items() if str(k).strip() and str(v).strip()}


def _resolved_health(source, by_name, aliases):
    if source in by_name:
        return by_name[source]
    successor = aliases.get(source)
    if successor and successor in by_name:
        return by_name[successor]
    return None


def manifest_coverage(source_health, path=CONFIG):
    required, expansion = load_target_sources(path)
    aliases = _source_aliases(path)
    by_name = {str(x.get("source") or "").strip(): x for x in source_health}
    represented = set(by_name)
    missing_required = [x for x in required if _resolved_health(x, by_name, aliases) is None]
    missing_expansion = [x for x in expansion if _resolved_health(x, by_name, aliases) is None]
    unhealthy_required = []
    for source in required:
        health = _resolved_health(source, by_name, aliases)
        if health and str(health.get("status") or "").upper() in {"FAILED", "NOT IMPLEMENTED", "MISSING"}:
            unhealthy_required.append(source)
    resolved_aliases = {
        source: successor for source, successor in aliases.items()
        if source in required + expansion and successor in by_name
    }
    return {
        "required_sources": required,
        "expansion_sources": expansion,
        "represented_sources": sorted(represented),
        "resolved_source_aliases": resolved_aliases,
        "missing_required_sources": missing_required,
        "missing_expansion_sources": missing_expansion,
        "unhealthy_required_sources": unhealthy_required,
        "required_coverage_pct": round(100 * (len(required) - len(missing_required)) / len(required), 1) if required else 100.0,
        "acceptance_ready": not missing_required and not unhealthy_required,
    }


def append_missing_health(source_health, path=CONFIG):
    required, expansion = load_target_sources(path)
    aliases = _source_aliases(path)
    by_name = {str(x.get("source") or "").strip(): x for x in source_health}

    # Preserve the original target-source identity in source-health while avoiding
    # a duplicate collector for brands that have been absorbed into a successor.
    for source in required + expansion:
        if source in by_name:
            continue
        successor = aliases.get(source)
        successor_health = by_name.get(successor) if successor else None
        if successor_health is None:
            continue
        alias_health = {
            "source": source,
            "status": "MERGED SOURCE",
            "lots_seen": successor_health.get("lots_seen", 0),
            "expected_count": successor_health.get("expected_count"),
            "discovered_count": successor_health.get("discovered_count"),
            "coverage_pct": successor_health.get("coverage_pct"),
            "authoritative_snapshot": successor_health.get("authoritative_snapshot", False),
            "scope_dates": list(successor_health.get("scope_dates") or []),
            "message": f"{source} is represented by successor source {successor}; inventory is collected there rather than duplicated.",
            "checked_at": successor_health.get("checked_at"),
            "successor_source": successor,
        }
        source_health.append(alias_health)
        by_name[source] = alias_health

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
            "message": "Required target source has no production collector. Acceptance is blocked until it is assessed and implemented, explicitly classified as catalogue-pending, or mapped to a verified successor source.",
            "checked_at": None,
        })
    return manifest_coverage(source_health, path)
