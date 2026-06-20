"""The two scheduled entry points (cron). NOT an always-on service.

  ingest_extract_triage()  — the frequent job (e.g. every few hours / early-morning
      + midday). Each adapter pulls only what's new since its cursor; records are
      extracted + graded; the Content-Based Router fires any urgent alert at the
      END of the run. Urgent latency == the cron interval, which satisfies a
      same-day / next-morning SLA with no real-time infrastructure.

  aggregate_and_digest()   — the weekly job. Clusters all accumulated candidates
      into themes (the single Claude clustering pass), ranks them, splits tiers,
      and renders the trend digest.

See cron/crontab.example for the cadences.
"""

from __future__ import annotations

from .adapters import registry
from .analysis.cluster import run_clustering
from .analysis.extract import run_extraction
from .surfacing.notifier import Notifier
from .triage.router import evaluate_and_route


def ingest_extract_triage(store, analyzer, notifier: Notifier, now: str) -> dict:
    new_records = []
    per_source = []
    for adapter in registry.active_adapters():
        cursor = store.get_cursor(adapter.source_name)
        records, new_cursor = adapter.poll(cursor)            # incremental polling
        store.set_cursor(adapter.source_name, new_cursor, now)
        per_source.append({"source": adapter.source_name, "new_records": len(records)})
        new_records.extend(records)

    candidates = run_extraction(new_records, analyzer, store, now)  # filter 1 (Claude)
    fired = evaluate_and_route(store, notifier, now)               # content-based router
    return {
        "per_source": per_source,
        "new_records": len(new_records),
        "new_candidates": len(candidates),
        "fired_alerts": fired,
    }


def _theme_score(t) -> float:
    """Blended ranking signal: severity weighted, plus frequency, plus a trend nudge."""
    trend_bonus = {"rising": 2, "new": 1.5, "steady": 0, "cooling": -1}.get(t.trend, 0)
    return t.max_severity * 2 + t.count + trend_bonus


def aggregate_and_digest(store, analyzer, notifier: Notifier, now: str, window: str) -> dict:
    themes = run_clustering(analyzer, store, now)                  # filter 2 (Claude)

    # route each theme through the SAME tier logic for the digest split
    urgent_categories = store.active_alert_categories()
    ranked = sorted(themes, key=_theme_score, reverse=True)
    trend_themes = [t for t in ranked if t.category not in urgent_categories]
    escalated = [t for t in ranked if t.category in urgent_categories]

    # persist themes + provenance for trust/verification
    for t in ranked:
        tier = "urgent" if t.category in urgent_categories else "trend"
        store.save_theme(t, tier, now)

    new_signal_count = sum(t.count for t in themes)
    notifier.send_digest(trend_themes, escalated, window, new_signal_count)
    return {"ranked": ranked, "trend": trend_themes, "escalated": escalated}
