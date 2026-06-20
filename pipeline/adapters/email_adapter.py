"""EmailAdapter — public, monitored, role-based inboxes only.

Shaping decision #1 (consent-by-design) is enforced HERE, at ingest:

  * Only public role inboxes are ever read. A hard allowlist
    (questions@ / talkback@ / volunteer@acc.eco) gates ingestion. A message to
    anything else — a personal inbox — is refused, never analyzed.
  * Each of those addresses carries a standing notice: "Messages to this address
    are reviewed to help us better support our branch leaders and brand
    ambassadors." That consent-by-design framing is the legitimacy basis recorded
    on every record, so no one is ever surveilled in private correspondence.
"""

from __future__ import annotations

import json
import os

from ..canonical import (
    ROLE_BRANCH_LEADER,
    SOURCE_EMAIL,
    CommunicationRecord,
)
from .base import SourceAdapter

_SAMPLE = os.path.join(os.path.dirname(__file__), "..", "..", "sample_data", "emails.json")

# Public, monitored, role-based addresses. NEVER personal/private inboxes.
_PUBLIC_ROLE_INBOXES = {
    "questions@acc.eco",
    "talkback@acc.eco",
    "volunteer@acc.eco",
}

_STANDING_NOTICE = (
    "Messages to this address are reviewed to help us better support our "
    "branch leaders and brand ambassadors."
)


class EmailAdapter(SourceAdapter):
    source_name = "role_inbox_gmail"

    def _fetch_raw(self) -> list:
        # STUBBED: in production this calls the Gmail API for each public role
        # inbox, e.g. users.messages.list/get for talkback@acc.eco with
        #   q="after:<cursor>"  (delegated, read-only scope on the shared mailbox)
        # The standing-notice auto-reply is configured on those mailboxes so the
        # consent framing is visible to every sender.
        with open(_SAMPLE, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def poll(self, since_cursor: str) -> tuple[list, str]:
        raw = self._fetch_raw()
        records, cursor = [], since_cursor
        for msg in raw:
            to_addr = msg["to"].lower().strip()
            if to_addr not in _PUBLIC_ROLE_INBOXES:
                # consent guard: refuse anything that is not a public role inbox
                continue
            received = msg["received_at"]
            if received <= since_cursor:
                continue
            records.append(
                CommunicationRecord(
                    record_id=f"email:{msg['message_id']}",
                    source_type=SOURCE_EMAIL,
                    source_adapter=self.source_name,
                    source_ref=f"gmail://{to_addr}/{msg['message_id']}",
                    channel=to_addr,
                    author_role=msg.get("from_role", ROLE_BRANCH_LEADER),
                    occurred_at=received,
                    consent_basis=f"public-inbox-standing-notice: {_STANDING_NOTICE}",
                    # subject + body are transient; analyzed then dropped
                    # ". " join so the subject reads as its own sentence
                    content=f"{msg.get('subject','').strip().rstrip('.')}. {msg['body']}",
                    metadata={"inbox": to_addr},
                )
            )
            cursor = max(cursor, received)
        return records, cursor
