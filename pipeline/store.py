"""Persistence — in-memory stub for the demo.

Production is PostgreSQL (schema.sql is the authoritative DDL). The demo keeps
state in memory so it needs no database — the same way the external integrations
(Fathom, Gmail, ...) are stubbed behind their adapters. A Postgres-backed
implementation drops in behind this identical interface.

Two design decisions are visible in the shape here:
  1. Data minimization — save_record keeps only channel/role/source metadata; the
     raw transcript or email body is never stored.
  2. Idempotency — per-source cursors back incremental polling, and alert state
     backs the dedup that stops an already-escalated theme re-alerting.
"""

from __future__ import annotations


class Store:
    def __init__(self, *_args, **_kwargs):
        self._cursors = {}
        self._records = {}      # record_id -> minimal metadata (no body)
        self._candidates = []   # PainPointCandidate objects
        self._themes = {}       # theme_key -> theme + evidence
        self._alerts = {}       # theme_key -> alert state

    @staticmethod
    def reset(*_args, **_kwargs) -> None:
        # nothing to reset — state lives only for the life of the process
        pass

    # --- cursors / watermarks (incremental, idempotent polling) ------------
    def get_cursor(self, source_name: str) -> str:
        return self._cursors.get(source_name, "1970-01-01T00:00:00Z")

    def set_cursor(self, source_name: str, watermark: str, now: str) -> None:
        self._cursors[source_name] = watermark

    # --- records (raw body intentionally dropped) -------------------------
    def save_record(self, rec) -> None:
        self._records.setdefault(rec.record_id, {
            "channel": rec.channel,
            "author_role": rec.author_role,
            "source_type": rec.source_type,
        })

    def record_meta(self, record_id: str) -> dict:
        return self._records.get(
            record_id, {"channel": "?", "author_role": "unknown", "source_type": "?"})

    # --- candidates -------------------------------------------------------
    def save_candidate(self, c, now: str) -> None:
        if not any(x.candidate_id == c.candidate_id for x in self._candidates):
            self._candidates.append(c)

    def all_candidates(self) -> list:
        return list(self._candidates)

    def category_rollup(self) -> list:
        """Per-category aggregate the frequent-job router keys on (count + max grade)."""
        agg = {}
        for c in self._candidates:
            a = agg.setdefault(c.category, {
                "category": c.category, "cnt": 0, "max_sev": 0, "max_urg": 0, "any_acute": 0})
            a["cnt"] += 1
            a["max_sev"] = max(a["max_sev"], c.severity)
            a["max_urg"] = max(a["max_urg"], c.urgency)
            a["any_acute"] = max(a["any_acute"], int(c.acute))
        return list(agg.values())

    def candidates_with_meta(self, category: str) -> list:
        rows = []
        for c in self._candidates:
            if c.category != category:
                continue
            m = self.record_meta(c.record_id)
            rows.append({
                "candidate_id": c.candidate_id, "record_id": c.record_id,
                "severity": c.severity, "acute": int(c.acute),
                "evidence_snippet": c.evidence_snippet,
                "channel": m["channel"], "author_role": m["author_role"],
                "source_type": m["source_type"],
            })
        rows.sort(key=lambda r: (r["severity"], r["acute"]), reverse=True)
        return rows

    # --- themes (weekly clustering output, with provenance) ---------------
    def save_theme(self, t, tier: str, now: str) -> None:
        self._themes[t.theme_key] = {
            "label": t.label, "category": t.category, "count": t.count,
            "tier": tier, "evidence": t.evidence,
        }

    # --- alert state (idempotent escalation; anti alarm-fatigue) ----------
    def get_active_alert(self, theme_key: str):
        a = self._alerts.get(theme_key)
        return a if a and a["status"] == "active" else None

    def record_alert(self, theme_key: str, tier: str, count: int, severity: int, now: str) -> None:
        existing = self._alerts.get(theme_key)
        first = existing["first_alerted_at"] if existing else now
        self._alerts[theme_key] = {
            "theme_key": theme_key, "tier": tier, "status": "active",
            "last_count": count, "last_severity": severity,
            "first_alerted_at": first, "last_alerted_at": now,
        }

    def active_alert_categories(self) -> set:
        # theme_key is "<category>:urgent"
        return {k.split(":", 1)[0] for k, v in self._alerts.items() if v["status"] == "active"}
