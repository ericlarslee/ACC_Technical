"""Extraction filter (Pipes-and-Filters stage 1 / Claude prompt #1).

Run PER record. For each new CommunicationRecord, Claude reads the content and
returns any pain-point candidates (or none). Then — and this is where data
minimization happens — we persist the record WITHOUT its body and persist each
candidate with just a short evidence snippet + a pointer back to the source.
The full transcript / email body is never written to storage.
"""

from __future__ import annotations


def run_extraction(records: list, analyzer, store, now: str) -> list:
    all_candidates = []
    for rec in records:
        candidates = analyzer.extract(rec)        # Claude prompt #1 (or mock)
        store.save_record(rec)                    # body dropped at the store boundary
        for c in candidates:
            store.save_candidate(c, now)
        all_candidates.extend(candidates)
    return all_candidates
