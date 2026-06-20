"""SourceAdapter — the Strategy interface every source implements."""

from __future__ import annotations

import abc

from ..canonical import CommunicationRecord


class SourceAdapter(abc.ABC):
    """One strategy per source. Each adapter:

      * knows how to *retrieve* what's new since the last run (scheduled polling
        against a stored per-source cursor/watermark — incremental + idempotent),
      * knows how to *normalize* its source payload into a CommunicationRecord,
      * declares the consent basis that makes analyzing this source legitimate.
    """

    #: stable name used as the cursor key in the store
    source_name: str = "base"
    #: flipped off for sources that are stubbed for the future
    enabled: bool = True

    @abc.abstractmethod
    def poll(self, since_cursor: str) -> tuple[list, str]:
        """Return (new_records, new_cursor).

        `since_cursor` is the last watermark we processed for this source. The
        adapter returns only records strictly newer than it, plus the advanced
        cursor to persist. Re-running with the same data returns nothing new."""
        raise NotImplementedError
