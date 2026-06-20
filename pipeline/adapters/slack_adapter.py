"""SlackAdapter — designated public ACC leader/ambassador Slack channels.

STUBBED FUTURE SOURCE. Disabled in the registry. Same interface, same canonical
record. Going live = implementing _fetch_raw() and flipping `enabled = True`.
"""

from __future__ import annotations

from .base import SourceAdapter


class SlackAdapter(SourceAdapter):
    source_name = "slack_channels"
    enabled = False  # deferred future integration

    def poll(self, since_cursor: str) -> tuple[list, str]:
        # STUBBED: in production this calls the Slack Web API
        #   conversations.history(channel=<designated public channel>, oldest=<cursor>)
        # for explicitly-designated channels only (consent_basis =
        # "designated-public-channel"), normalizing each message into a
        # CommunicationRecord. Returns nothing today.
        return [], since_cursor
