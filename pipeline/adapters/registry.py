"""Config-driven source registry.

The pipeline iterates whatever the registry hands it. Turning a source on/off,
or adding a new one, is a config edit here — never a change to the pipeline,
triage, or surfacing code (open for extension, closed for modification).
"""

from __future__ import annotations

from .email_adapter import EmailAdapter
from .forms_adapter import FormsAdapter
from .slack_adapter import SlackAdapter
from .transcript_adapter import TranscriptAdapter

# Declarative registration. Order is ingest order; `enabled` gates activation.
_REGISTERED = [
    TranscriptAdapter,   # Zoom/Fathom targeted calls        (live)
    EmailAdapter,        # public role inboxes               (live)
    FormsAdapter,        # Google Forms                      (stubbed / future)
    SlackAdapter,        # designated Slack channels         (stubbed / future)
]


def active_adapters() -> list:
    """Instantiate the adapters that are enabled."""
    return [cls() for cls in _REGISTERED if getattr(cls, "enabled", True)]


def describe_registry() -> list:
    return [
        {"source_name": cls.source_name, "enabled": getattr(cls, "enabled", True),
         "adapter": cls.__name__}
        for cls in _REGISTERED
    ]
