"""Where Claude sits: the two prompts, behind one swappable interface.

`ClaudeAnalyzer` has two methods — `extract` (prompt #1, per record) and
`cluster` (prompt #2, once per batch). Two implementations satisfy it:

  * AnthropicAnalyzer — the real thing. Builds the prompts and calls Claude with
    structured-output JSON schemas (models right-sized per stage; see below).
  * MockAnalyzer — a clearly-marked deterministic stand-in at the SAME interface,
    so the demo runs offline and reproducibly. It mimics what Claude returns.

Swap is a one-line change (the ACC_USE_REAL_CLAUDE env var), because both speak
the identical interface and the identical JSON shapes.
"""

from __future__ import annotations

import json
import os
import re

from ..canonical import (
    CATEGORY_LABELS,
    PainPointCandidate,
    clamp_grade,
)

EXTRACT_MODEL = os.environ.get("ACC_EXTRACT_MODEL", "claude-sonnet-4-6")
CLUSTER_MODEL = os.environ.get("ACC_CLUSTER_MODEL", "claude-sonnet-4-6")

# --- structured-output JSON schemas (shared by real + mock as the contract) --
# Note: structured outputs don't support numeric min/max, so the 1-5 bounds are
# stated in the prompt and clamped in code (clamp_grade).
EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "pain_points": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category": {"type": "string", "enum": list(CATEGORY_LABELS.keys())},
                    "issue_text": {"type": "string"},
                    "severity": {"type": "integer"},
                    "urgency": {"type": "integer"},
                    "evidence_snippet": {"type": "string"},
                    "confidence": {"type": "number"},
                    "acute": {"type": "boolean"},
                },
                "required": ["category", "issue_text", "severity", "urgency",
                             "evidence_snippet", "confidence", "acute"],
            },
        }
    },
    "required": ["pain_points"],
}

CLUSTER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "themes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string"},
                    "category": {"type": "string", "enum": list(CATEGORY_LABELS.keys())},
                    "underlying_issue": {"type": "string"},
                    "candidate_ids": {"type": "array", "items": {"type": "string"}},
                    "trend": {"type": "string", "enum": ["rising", "steady", "new", "cooling"]},
                },
                "required": ["label", "category", "underlying_issue", "candidate_ids", "trend"],
            },
        }
    },
    "required": ["themes"],
}

EXTRACTION_SYSTEM = (
    "You read ONE communication from an ACC branch leader or brand ambassador and "
    "surface the lived, human friction in it — feeling unsupported at events, slow "
    "reimbursement, unclear communication from national, onboarding confusion, "
    "burnout, questions that went unanswered. These are experiential pain points, "
    "NOT technical bug reports. Most records contain nothing; when so, return an "
    "empty list. For each real pain point return: category, a generalized issue_text, "
    "a severity (1 papercut .. 5 acute), an urgency (1 whenever .. 5 same-day), a short "
    "verbatim evidence_snippet, a confidence (0..1), and acute=true ONLY when the person "
    "signals they may step back, walk, or quit. Output ONLY the JSON."
)

CLUSTER_SYSTEM = (
    "You are given a batch of already-extracted pain-point candidates from ACC "
    "branch leaders and brand ambassadors. Group them into recurring themes and "
    "dedup: the same issue raised five times becomes ONE theme listing all five "
    "candidate_ids. For each theme give a human label, the category, a short "
    "underlying_issue, the member candidate_ids, and a trend (new / rising / steady / "
    "cooling). Output ONLY the JSON."
)


def _split_sentences(text: str) -> list:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


# ===========================================================================
#  REAL implementation — calls Claude
# ===========================================================================
class AnthropicAnalyzer:
    """Production analyzer. `import anthropic` is lazy so the mock path needs no dep."""

    def __init__(self):
        import anthropic  # lazy
        self.client = anthropic.Anthropic()

    def extract(self, record) -> list:
        rendered = (
            f"SOURCE: {record.source_type} via {record.channel}\n"
            f"AUTHOR ROLE: {record.author_role}\n"
            f"WHEN: {record.occurred_at}\n\n{record.content}"
        )
        resp = self.client.messages.create(
            model=EXTRACT_MODEL,
            max_tokens=1024,
            system=EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": rendered}],
            output_config={"format": {"type": "json_schema", "schema": EXTRACTION_SCHEMA}},
        )
        text = next(b.text for b in resp.content if b.type == "text")
        data = json.loads(text)
        out = []
        for i, pp in enumerate(data.get("pain_points", [])):
            out.append(PainPointCandidate(
                candidate_id=f"cand:{record.record_id}:{i}",
                record_id=record.record_id,
                category=pp["category"],
                issue_text=pp["issue_text"],
                severity=clamp_grade(pp["severity"]),
                urgency=clamp_grade(pp["urgency"]),
                evidence_snippet=pp["evidence_snippet"][:200],
                confidence=float(pp.get("confidence", 0.7)),
                acute=bool(pp.get("acute", False)),
            ))
        return out

    def cluster(self, candidates: list) -> list:
        rendered = "\n".join(
            f"- id={c.candidate_id} category={c.category} severity={c.severity} "
            f"acute={c.acute} :: {c.issue_text} (\"{c.evidence_snippet}\")"
            for c in candidates
        )
        resp = self.client.messages.create(
            model=CLUSTER_MODEL,
            max_tokens=4096,
            system=CLUSTER_SYSTEM,
            # Sonnet 4.6 supports adaptive thinking + effort; both are GA, no beta.
            thinking={"type": "adaptive"},
            output_config={"effort": "medium",
                           "format": {"type": "json_schema", "schema": CLUSTER_SCHEMA}},
            messages=[{"role": "user", "content": rendered}],
        )
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text).get("themes", [])


# ===========================================================================
#  MOCK implementation — a clearly-marked stand-in at the SAME interface
# ===========================================================================
class MockAnalyzer:
    """Deterministic stand-in for Claude. Produces realistically-shaped output so
    the demo runs offline. NOT a model — a small scoring classifier (word-boundary
    keyword hits per category, strongest category wins, with a corroboration gate)
    that mimics what the two Claude prompts would return on this sample set."""

    _ATTRITION = ("about to walk", "step back", "stepping back", "considering stepping",
                  "seriously considering", "ready to quit", "i'm done", "im done",
                  "calling it quits", "last straw", "walk away", "thinking about leaving")

    # category -> distinctive keyword/phrase patterns (matched at a word boundary)
    _RULES = {
        "reimbursement": ("reimburs", "expense", "out of pocket", "out-of-pocket",
                          "owed", "paid back", "money back", "receipts", "fronting", "$"),
        "event_support": ("materials", "booth", "understaffed", "point of contact",
                          "felt alone", "alone at", "on my own", "promised", "unsupported",
                          "no support", "on site", "no one i could call", "no banner"),
        "national_comms": ("conflicting", "newsletter", "coordinator", "sporadic",
                           "who to ask", "mixed messages", "unclear", "source of truth",
                           "communication from national", "national contacts",
                           "out of the loop", "radio silence"),
        "onboarding": ("onboard", "new ambassador", "new branch", "get started",
                       "getting started", "packet", "ramp up", "first few weeks",
                       "lost for weeks", "out of date"),
        "burnout": ("burn out", "burning out", "burnt out", "stretched thin", "exhausted",
                    "overwhelmed", "spread too thin", "running on empty", "running on fumes",
                    "basically solo"),
    }

    # priority order used to break score ties deterministically
    _ORDER = ("reimbursement", "event_support", "national_comms", "onboarding", "burnout")

    _BASE = {  # (severity, urgency) before acute escalation
        "reimbursement": (3, 3),
        "event_support": (3, 2),
        "national_comms": (2, 2),
        "onboarding": (2, 2),
        "burnout": (3, 2),
    }

    _ISSUE = {
        "reimbursement": "Reimbursement / expense repayment is slow or unanswered",
        "event_support": "Felt unsupported or under-resourced at an event",
        "national_comms": "Communication from national is unclear or inconsistent",
        "onboarding": "Onboarding / getting started was confusing",
        "burnout": "Overextended and heading toward burnout",
    }

    # Mocked prior-week counts — in production trend = compare to the previous
    # aggregation's persisted theme.count snapshot.
    _PRIOR_WEEK = {"reimbursement": 2, "event_support": 3, "national_comms": 1,
                   "onboarding": 0, "burnout": 0}

    @staticmethod
    def _matches(pattern: str, text: str) -> bool:
        if pattern == "$":
            return "$" in text
        # leading word boundary only, so stems like "reimburs" still match
        # "reimbursement" while "owed" does NOT match "showed"
        return re.search(r"\b" + re.escape(pattern), text) is not None

    def extract(self, record) -> list:
        low = record.content.lower()
        acute = any(p in low for p in self._ATTRITION)

        # score every category by how many distinct signals it matched
        scored = []
        matched_patterns: dict = {}
        for cat in self._ORDER:
            hits = [p for p in self._RULES[cat] if self._matches(p, low)]
            if hits:
                scored.append((cat, len(hits)))
                matched_patterns[cat] = hits
        if not scored:
            return []

        scored.sort(key=lambda x: (-x[1], self._ORDER.index(x[0])))
        category, score = scored[0]

        # corroboration gate: require two signals, OR one signal + an attrition
        # cue. This keeps positive/noise records ("great event", "logo files")
        # from being flagged when they happen to share a single word.
        if score < 2 and not acute:
            return []

        sev, urg = self._BASE[category]
        issue = self._ISSUE[category]
        if acute:
            sev, urg = 5, 5
            issue += " — person signals they may step back / leave"

        # evidence quote = first sentence containing any matched signal
        cues = matched_patterns[category]
        snippet = next(
            (s for s in _split_sentences(record.content)
             if any(self._matches(c, s.lower()) for c in cues)),
            record.content[:160],
        )
        snippet = " ".join(snippet.split()).strip('"')[:200]

        return [PainPointCandidate(
            candidate_id=f"cand:{record.record_id}",
            record_id=record.record_id,
            category=category,
            issue_text=issue,
            severity=clamp_grade(sev),
            urgency=clamp_grade(urg),
            evidence_snippet=snippet,
            confidence=0.9 if acute else 0.8,
            acute=acute,
        )]

    def cluster(self, candidates: list) -> list:
        by_cat: dict = {}
        for c in candidates:
            by_cat.setdefault(c.category, []).append(c)

        themes = []
        for cat, members in by_cat.items():
            count = len(members)
            prior = self._PRIOR_WEEK.get(cat, 0)
            if prior == 0:
                trend = "new"
            elif count > prior:
                trend = "rising"
            elif count < prior:
                trend = "cooling"
            else:
                trend = "steady"
            # underlying issue = the non-acute base statement for the category
            underlying = self._ISSUE.get(cat, CATEGORY_LABELS.get(cat, cat))
            themes.append({
                "label": CATEGORY_LABELS.get(cat, cat),
                "category": cat,
                "underlying_issue": underlying,
                "candidate_ids": [c.candidate_id for c in members],
                "trend": trend,
            })
        return themes


def get_analyzer():
    """Factory. Real Claude when explicitly enabled AND a key is present; the
    clearly-mocked equivalent otherwise (the demo default)."""
    if os.environ.get("ACC_USE_REAL_CLAUDE") == "1" and os.environ.get("ANTHROPIC_API_KEY"):
        return (AnthropicAnalyzer(),
                f"AnthropicAnalyzer (real Claude — extract={EXTRACT_MODEL}, cluster={CLUSTER_MODEL})")
    return MockAnalyzer(), "MockAnalyzer (clearly-mocked Claude equivalent, same interface)"
