"""Clustering filter (Pipes-and-Filters stage 2 / Claude prompt #2).

Run ONCE per aggregation over all accumulated candidates. Claude groups them into
recurring themes and dedups (the same issue raised five times becomes one theme
with count 5). The pipeline then assembles each Theme with FULL provenance —
count, max grade, and the evidence snippets/record pointers behind it — so
leadership can trust and verify every theme.
"""

from __future__ import annotations

from ..canonical import CATEGORY_LABELS, Theme


def run_clustering(analyzer, store, now: str) -> list:
    candidates = store.all_candidates()
    if not candidates:
        return []
    by_id = {c.candidate_id: c for c in candidates}

    groups = analyzer.cluster(candidates)        # Claude prompt #2 (or mock)

    themes = []
    for g in groups:
        members = [by_id[cid] for cid in g["candidate_ids"] if cid in by_id]
        if not members:
            continue
        category = g["category"]
        evidence = []
        for c in members:
            meta = store.record_meta(c.record_id)
            evidence.append({
                "candidate_id": c.candidate_id,
                "record_id": c.record_id,
                "snippet": c.evidence_snippet,
                "channel": meta["channel"],
                "author_role": meta["author_role"],
                "severity": c.severity,
                "acute": c.acute,
            })
        # strongest evidence first
        evidence.sort(key=lambda e: (e["acute"], e["severity"]), reverse=True)

        theme = Theme(
            theme_key=f"{category}:weekly",
            label=g.get("label", CATEGORY_LABELS.get(category, category)),
            category=category,
            count=len(members),
            underlying_issue=g.get("underlying_issue", ""),
            max_severity=max(c.severity for c in members),
            max_urgency=max(c.urgency for c in members),
            candidate_ids=[c.candidate_id for c in members],
            evidence=evidence,
            trend=g.get("trend", "steady"),
            acute=any(c.acute for c in members),
        )
        themes.append(theme)
    return themes
