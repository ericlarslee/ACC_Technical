"""Canonical Data Model.

Every source adapter normalizes its source-specific payload into ONE shape —
the CommunicationRecord — so the rest of the pipeline never has to know whether
a signal came from a Fathom transcript, a role inbox, a Google Form, or Slack.
Adding a new source means writing a new adapter, not touching the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- source types (one per adapter) ---------------------------------------
SOURCE_TRANSCRIPT = "transcript"
SOURCE_EMAIL = "email"
SOURCE_FORM = "form"      # stubbed future source
SOURCE_SLACK = "slack"    # stubbed future source

# --- author roles (aggregate only — never a named individual) --------------
ROLE_BRANCH_LEADER = "branch_leader"
ROLE_BRAND_AMBASSADOR = "brand_ambassador"
ROLE_UNKNOWN = "unknown"

# --- pain-point taxonomy ---------------------------------------------------
# These are the *lived friction* categories, not technical bug categories.
CATEGORIES = [
    "reimbursement",
    "event_support",
    "national_comms",
    "onboarding",
    "burnout",
    "unanswered_question",
    "other",
]

CATEGORY_LABELS = {
    "reimbursement": "Reimbursement delays",
    "event_support": "Feeling unsupported at events",
    "national_comms": "Unclear / inconsistent communication from national",
    "onboarding": "Onboarding confusion for new leaders",
    "burnout": "Volunteer burnout / overextension",
    "unanswered_question": "Questions going unanswered",
    "other": "Other friction",
}


@dataclass
class CommunicationRecord:
    """The single canonical record every adapter emits."""

    record_id: str           # stable id, e.g. "email:talkback:2026-06-15:003"
    source_type: str         # SOURCE_* constant
    source_adapter: str      # which adapter produced it (provenance)
    source_ref: str          # pointer back to the source system (URL / message-id / transcript id)
    channel: str             # public role inbox address, or targeted-call title
    author_role: str         # ROLE_* — aggregate role, never PII
    occurred_at: str         # ISO-8601; doubles as the polling watermark
    consent_basis: str       # WHY we are permitted to analyze this signal
    content: str             # TRANSIENT: read in-memory for extraction, NEVER warehoused
    metadata: dict = field(default_factory=dict)


@dataclass
class PainPointCandidate:
    """One graded pain-point extracted by Claude from a single record."""

    candidate_id: str
    record_id: str           # provenance pointer back to the source record
    category: str
    issue_text: str          # generalized statement of the friction
    severity: int            # 1 (papercut) .. 5 (acute)
    urgency: int             # 1 (whenever) .. 5 (same-day)
    evidence_snippet: str    # short verbatim quote, kept for trust/verification
    confidence: float
    acute: bool = False      # signals an attrition / "about to walk" moment


@dataclass
class Theme:
    """A recurring theme: many candidates about the same underlying friction."""

    theme_key: str
    label: str
    category: str
    count: int
    underlying_issue: str
    max_severity: int
    max_urgency: int
    candidate_ids: list      # full lineage: which candidates belong to this theme
    evidence: list           # [{snippet, record_id, channel, author_role}], aggregate provenance
    trend: str = "steady"    # rising | steady | new | cooling
    acute: bool = False


def clamp_grade(value: int) -> int:
    """Defensive clamp so a model never routes on an out-of-range grade."""
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return 1
