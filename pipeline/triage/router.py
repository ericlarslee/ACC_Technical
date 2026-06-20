"""Content-Based Router + idempotent alert state.

Routing keys on the grade (severity/urgency) plus a cheap velocity signal:

  URGENT  when  max_severity >= URGENT_SEVERITY_THRESHOLD   (a single acute
                grievance, e.g. an ambassador signaling they're about to walk)
          OR    there is any acute candidate in the category
          OR    count >= SPREAD_COUNT_THRESHOLD AND max_severity >= SPREAD_FLOOR
                (a fast-spreading cluster of the same grievance)
  TREND   otherwise (recurring friction, mild dissatisfaction, papercuts)

Idempotency: once an urgent alert fires for a theme, alert_state remembers it.
A later run re-fires ONLY if the cluster has grown by >= REALERT_DELTA new
signals (material escalation). Otherwise it is suppressed — no re-alerting the
same fire every few hours.
"""

from __future__ import annotations

from ..canonical import CATEGORY_LABELS

URGENT_SEVERITY_THRESHOLD = 4   # a high-severity single grievance
SPREAD_COUNT_THRESHOLD = 4      # a cluster of leaders voicing the same thing
SPREAD_SEVERITY_FLOOR = 3       # ...that is at least moderately severe
REALERT_DELTA = 3               # only re-fire if it has grown this much


def decide_tier(rollup_row: dict) -> str:
    sev = rollup_row["max_sev"]
    cnt = rollup_row["cnt"]
    acute = bool(rollup_row["any_acute"])
    if sev >= URGENT_SEVERITY_THRESHOLD or acute:
        return "urgent"
    if cnt >= SPREAD_COUNT_THRESHOLD and sev >= SPREAD_SEVERITY_FLOOR:
        return "urgent"
    return "trend"


def evaluate_and_route(store, notifier, now: str) -> list:
    """Run at the end of an ingest-triage job. Returns the list of fired alerts."""
    fired = []
    for row in store.category_rollup():
        tier = decide_tier(row)
        if tier != "urgent":
            continue  # trend-tier themes are simply accumulated for the weekly digest

        category = row["category"]
        theme_key = f"{category}:urgent"
        existing = store.get_active_alert(theme_key)

        # idempotency / anti alarm-fatigue: suppress unless materially escalated
        if existing and (row["cnt"] - existing["last_count"]) < REALERT_DELTA:
            continue

        evidence = store.candidates_with_meta(category)
        reason = _why(row)
        alert = {
            "theme_key": theme_key,
            "category": category,
            "label": CATEGORY_LABELS.get(category, category),
            "count": row["cnt"],
            "max_severity": row["max_sev"],
            "acute": bool(row["any_acute"]),
            "reason": reason,
            "evidence": evidence,
            "is_reescalation": existing is not None,
        }
        notifier.send_urgent(alert)
        store.record_alert(theme_key, tier, row["cnt"], row["max_sev"], now)
        fired.append(alert)
    return fired


def _why(row: dict) -> str:
    sev, cnt, acute = row["max_sev"], row["cnt"], bool(row["any_acute"])
    bits = []
    if acute or sev >= URGENT_SEVERITY_THRESHOLD:
        bits.append("high-severity signal (someone may step back/leave)" if acute
                    else f"high-severity grade ({sev}/5)")
    if cnt >= SPREAD_COUNT_THRESHOLD and sev >= SPREAD_SEVERITY_FLOOR:
        bits.append(f"fast-spreading — {cnt} leaders/ambassadors raised it this cycle")
    return "; ".join(bits) or "crossed the urgent threshold"
