#!/usr/bin/env python3
"""ACC Voices — single batch-pass demo over canned sample data.

Runs the whole pipeline end to end through the stubbed adapters:

    1. ingest -> extract (Claude prompt #1) -> grade -> route   [frequent job]
       ...firing same-day URGENT alerts for anything over threshold
    2. cluster (Claude prompt #2) -> rank -> render             [weekly job]
       ...producing the ranked theme list + the weekly trend digest
    3. re-run the frequent job to demonstrate idempotency
       ...nothing new ingested, no duplicate alerts (anti alarm-fatigue)

By default it uses the clearly-mocked Claude equivalent so it runs offline and
deterministically. Set ACC_USE_REAL_CLAUDE=1 (with ANTHROPIC_API_KEY) to use the
real model through the identical interface.

Usage:
    python run_demo.py
"""

from __future__ import annotations

import datetime
import os

from pipeline.adapters import registry
from pipeline.analysis.claude_client import get_analyzer
from pipeline.jobs import aggregate_and_digest, ingest_extract_triage
from pipeline.store import Store
from pipeline.surfacing.notifier import Notifier

BASE_DIR = os.path.dirname(__file__)


def banner(title: str) -> None:
    print("\n" + "*" * 72)
    print(f"  {title}")
    print("*" * 72 + "\n")


def main() -> None:
    store = Store()   # in-memory stub; PostgreSQL in production (see schema.sql)
    analyzer, analyzer_name = get_analyzer()
    # stubbed (mock) and real-Claude runs write to separate report folders
    is_mock = type(analyzer).__name__ == "MockAnalyzer"
    output_dir = os.path.join(BASE_DIR, "sample-reports",
                              "stubbed" if is_mock else "real-claude")
    now = datetime.datetime.now().isoformat(timespec="seconds")
    window = "the last 7 days"

    banner("ACC VOICES — passive pain-point surfacing (single batch pass)")
    print(f"Analyzer:  {analyzer_name}")
    print("Sources registered (config-driven registry):")
    for s in registry.describe_registry():
        state = "ENABLED " if s["enabled"] else "stubbed "
        print(f"  [{state}] {s['adapter']:<18} ({s['source_name']})")

    # ---- JOB 1: frequent ingest -> extract -> grade -> route --------------
    banner("CRON JOB 1 (frequent)  —  ingest · extract · grade · route")
    notifier = Notifier()
    r1 = ingest_extract_triage(store, analyzer, notifier, now)
    print("Ingest (incremental, per source cursor):")
    for ps in r1["per_source"]:
        print(f"  {ps['source']:<22} +{ps['new_records']} new record(s)")
    print(f"\nExtraction: {r1['new_candidates']} pain-point candidate(s) "
          f"from {r1['new_records']} record(s) "
          f"(most records yield nothing — that's expected).")
    print(f"Router fired {len(r1['fired_alerts'])} URGENT alert(s) at end of run:\n")
    if not r1["fired_alerts"]:
        print("  (none crossed the urgent threshold)")

    # ---- JOB 2: weekly aggregate -> cluster -> rank -> digest -------------
    banner("CRON JOB 2 (weekly)  —  cluster · rank · digest")
    r2 = aggregate_and_digest(store, analyzer, notifier, now, window)

    print("\nRanked recurring pain-point themes (severity · frequency · trend · evidence):\n")
    for i, t in enumerate(r2["ranked"], 1):
        tier = "URGENT" if t.category in store.active_alert_categories() else "trend"
        print(f"  {i}. {t.label}")
        print(f"       tier={tier}  count={t.count}  max_severity={t.max_severity}/5  "
              f"trend={t.trend}  acute={t.acute}")
        print(f"       provenance: {len(t.evidence)} evidence snippet(s) -> source records")
    print()

    # ---- JOB 1 again: demonstrate idempotency -----------------------------
    banner("CRON JOB 1 again  —  proving idempotency (next scheduled run)")
    quiet = Notifier()
    r3 = ingest_extract_triage(store, analyzer, quiet, now)
    print(f"Ingest: {r3['new_records']} new record(s) "
          f"(cursors advanced last run -> nothing new).")
    print(f"Router fired {len(r3['fired_alerts'])} new alert(s) "
          f"(already-escalated themes are suppressed -> no alarm fatigue).")

    # ---- persist the artifacts grassroots leadership received (HTML) ------
    urgent_path, digest_path = notifier.write_html(output_dir)

    banner("DONE")
    print(f"Artifacts written (open in a browser for the presentation):\n"
          f"  {urgent_path}\n  {digest_path}")
    print("Store: in-memory stub (PostgreSQL in production — see schema.sql)")


if __name__ == "__main__":
    main()
