"""FormsAdapter — Google Forms survey responses.

STUBBED FUTURE SOURCE. Disabled in the registry. It exists to show that a new
source plugs into the *same* SourceAdapter interface and emits the *same*
CommunicationRecord — adding it for real is writing _fetch_raw() and flipping
`enabled = True`, with zero changes to the pipeline, triage, or surfacing.
"""

from __future__ import annotations

from .base import SourceAdapter


class FormsAdapter(SourceAdapter):
    source_name = "google_forms"
    enabled = False  # deferred future integration

    def poll(self, since_cursor: str) -> tuple[list, str]:
        # STUBBED: in production this calls the Google Forms API
        #   forms.responses.list(formId, filter="timestamp > <cursor>")
        # and normalizes each structured response into a CommunicationRecord
        # (consent_basis = "survey-participation-consent"). Returns nothing today.
        return [], since_cursor
