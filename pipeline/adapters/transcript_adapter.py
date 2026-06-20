"""TranscriptAdapter — Zoom / Fathom meeting transcripts.

Targeted ingestion (shaping decision #2): we do NOT ingest every meeting on the
calendar. We ingest the calls where candid role friction actually surfaces —
post-event debriefs and calls with branch leaders / brand ambassadors. The
adapter filters to those (the `targeted` flag) and drops the rest.
"""

from __future__ import annotations

import json
import os

from ..canonical import (
    SOURCE_TRANSCRIPT,
    CommunicationRecord,
)
from .base import SourceAdapter

_SAMPLE = os.path.join(os.path.dirname(__file__), "..", "..", "sample_data", "transcripts.json")

# Meeting types we deliberately listen to. Everything else is ignored.
_TARGETED_TYPES = {"post_event_debrief", "branch_leader_call", "ambassador_call"}


class TranscriptAdapter(SourceAdapter):
    source_name = "fathom_transcripts"

    def _fetch_raw(self) -> list:
        # STUBBED: in production this calls the Fathom API (or Zoom Cloud
        # Recording + AI notes) for transcripts of *targeted* calls only, e.g.
        #   GET https://api.fathom.video/v1/meetings?type=debrief&since=<cursor>
        # then pulls each transcript by id. The return shape below matches what
        # that call yields closely enough that going live is a one-method change.
        with open(_SAMPLE, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def poll(self, since_cursor: str) -> tuple[list, str]:
        raw = self._fetch_raw()
        records, cursor = [], since_cursor
        for item in raw:
            # targeted-ingestion gate: skip non-debrief / non-leader meetings
            if item.get("meeting_type") not in _TARGETED_TYPES or not item.get("targeted", False):
                continue
            occurred = item["recorded_at"]
            if occurred <= since_cursor:           # incremental: only what's new
                continue
            records.append(
                CommunicationRecord(
                    record_id=f"transcript:{item['id']}",
                    source_type=SOURCE_TRANSCRIPT,
                    source_adapter=self.source_name,
                    source_ref=item.get("share_url", f"fathom://{item['id']}"),
                    channel=item["title"],
                    author_role=item.get("speaker_role", "branch_leader"),
                    occurred_at=occurred,
                    consent_basis="targeted-debrief-consent",
                    # body is transient; it is read for extraction then dropped
                    content=item["transcript_excerpt"],
                    metadata={"meeting_type": item["meeting_type"]},
                )
            )
            cursor = max(cursor, occurred)
        return records, cursor
