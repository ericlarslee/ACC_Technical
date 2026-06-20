"""Tiered notification renderer.

Renders the two artifacts grassroots leadership actually receives. In production
`_emit` is a Slack `chat.postMessage` to the leadership channel and/or an email
send; here it prints the text to the console (so the demo is readable in a
terminal) AND captures the structured data so `write_html` can render the same
artifacts as styled HTML files for presenting.

Surfacing rules baked in:
  * aggregate themes, never individual attribution ("five branch leaders flagged
    reimbursement delays", not a named complaint),
  * raw evidence is referenced as being behind access control,
  * a human-in-the-loop gate before anything outward-facing.
"""

from __future__ import annotations

import html as _html
import os

_TREND_GLYPH = {"rising": "UP rising", "steady": "-- steady",
                "new": "* new", "cooling": "v cooling"}

# trend -> (html symbol, css class)
_TREND_HTML = {"rising": ("&#8593;", "trend-rising"), "steady": ("&#8594;", "trend-steady"),
               "new": ("&#10022;", "trend-new"), "cooling": ("&#8595;", "trend-cooling")}


class Notifier:
    def __init__(self):
        self.artifacts = []   # captured text (console + tests)
        self._urgent = []     # captured urgent alert dicts (for HTML)
        self._digest = None   # (trend_themes, escalated, window, count) for HTML

    def _emit(self, text: str) -> None:
        # STUBBED transport: in production -> Slack chat.postMessage to the
        # grassroots-leadership channel and/or an email to the leadership alias.
        self.artifacts.append(text)
        print(text)
        print()

    # ---- URGENT tier (same-day, fired during ingest-triage) ---------------
    def send_urgent(self, alert: dict) -> None:
        ev = alert["evidence"]
        head = "RE-ESCALATION (materially grown)" if alert.get("is_reescalation") else \
               "URGENT — same-day escalation"
        lines = [
            "=" * 72,
            f"[ACC Voices]  {head}",
            "=" * 72,
            f"Theme:    {alert['label']}",
            f"Severity: {alert['max_severity']}/5     "
            f"Reach: {alert['count']} leader(s)/ambassador(s) this cycle",
            f"Why now:  {alert['reason']}",
            "",
            "What's happening (aggregate — no individual is named):",
            f"  A cluster of branch leaders / brand ambassadors are voicing the same",
            f"  unresolved friction around {alert['label'].lower()}.",
            "",
            "Evidence (aggregate; raw detail sits behind access control):",
        ]
        for e in ev[:4]:
            tag = "  [RETENTION RISK] " if e.get("acute") else "  - "
            lines.append(f'{tag}"{e["evidence_snippet"]}"')
            lines.append(f"        -- {e['author_role']}, {e['channel']}")
        if len(ev) > 4:
            lines.append(f"  (+{len(ev) - 4} more signals behind access control)")
        lines += [
            "",
            "HUMAN-IN-THE-LOOP: this internal alert fired automatically. Any outreach",
            "to the leaders/ambassadors themselves waits on a human reviewer",
            "(review-before-act).  ->  review_required = True",
            "Suggested owner: Grassroots Leadership (on-call)",
            "=" * 72,
        ]
        self._emit("\n".join(lines))
        self._urgent.append(alert)

    # ---- TREND tier (weekly digest) ---------------------------------------
    def send_digest(self, trend_themes: list, escalated_themes: list, window: str,
                    new_signal_count: int) -> None:
        lines = [
            "#" * 72,
            "ACC Voices — WEEKLY IMPROVEMENT DIGEST",
            f"Window: {window}",
            "Sources: Zoom/Fathom debriefs + public role inboxes "
            "(questions@/talkback@/volunteer@)",
            f"New pain-point signals this week: {new_signal_count}",
            "#" * 72,
            "",
            "This is about steady improvement, not emergencies. Ranked by a blended",
            "severity + frequency + trend signal:",
            "",
        ]
        if not trend_themes:
            lines.append("  (no trend-tier themes this week)")
        for i, t in enumerate(trend_themes, 1):
            lines.append(f"{i}. {t.label}   [{_TREND_GLYPH.get(t.trend, t.trend)}]")
            lines.append(f"     Reach: {t.count}   Severity: {t.max_severity}/5")
            lines.append(f"     Issue: {t.underlying_issue}")
            lines.append("     Evidence (aggregate; raw detail behind access control):")
            for e in t.evidence[:2]:
                lines.append(f'       - "{e["snippet"]}"')
                lines.append(f"         -- {e['author_role']}, {e['channel']}")
            lines.append("")

        if escalated_themes:
            lines.append("Already escalated this week (shown for context — see urgent alerts):")
            for t in escalated_themes:
                lines.append(
                    f"   - {t.label} — {t.count} signals, severity {t.max_severity}/5 "
                    f"(URGENT alert already fired)"
                )
            lines.append("")

        lines.append("#" * 72)
        self._emit("\n".join(lines))
        self._digest = (trend_themes, escalated_themes, window, new_signal_count)

    # ---- HTML artifacts (for presenting) ----------------------------------
    def write_html(self, output_dir: str):
        """Render the captured alerts + digest as two styled HTML files and
        return their paths."""
        os.makedirs(output_dir, exist_ok=True)

        if self._urgent:
            body = "".join(_urgent_card(a) for a in self._urgent)
        else:
            body = '<p class="empty">No themes crossed the urgent threshold this run.</p>'
        urgent_doc = _page(
            "ACC Voices — Urgent Alerts",
            "Same-day / next-morning escalations fired by the ingest-triage run.",
            "", body)
        urgent_path = os.path.join(output_dir, "urgent_alerts.html")
        with open(urgent_path, "w", encoding="utf-8") as fh:
            fh.write(urgent_doc)

        if self._digest:
            digest_doc = _digest_doc(*self._digest)
        else:
            digest_doc = _page("ACC Voices — Weekly Improvement Digest",
                               "No digest generated.", "", "")
        digest_path = os.path.join(output_dir, "weekly_digest.html")
        with open(digest_path, "w", encoding="utf-8") as fh:
            fh.write(digest_doc)

        return urgent_path, digest_path


# ===========================================================================
#  HTML rendering helpers
# ===========================================================================
def _esc(value) -> str:
    return _html.escape(str(value), quote=True)


_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f4f6f4;color:#1b211b;
  font:16px/1.55 -apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;padding:36px 18px;}
.wrap{max-width:880px;margin:0 auto;}
header.page h1{margin:0 0 4px;font-size:27px;letter-spacing:-.01em;}
header.page .sub{color:#5d6b5d;font-size:14px;}
.meta{color:#5d6b5d;font-size:13px;margin-top:8px;}
.card{background:#fff;border:1px solid #e2e7e2;border-radius:12px;padding:20px 22px;
  margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,.05);}
.card.urgent{border-left:6px solid #c62828;}
.card.trend{border-left:6px solid #2e7d32;}
.card h2{margin:6px 0 8px;font-size:20px;}
.badges{display:flex;gap:8px;flex-wrap:wrap;}
.badge{font-size:12px;font-weight:600;padding:3px 11px;border-radius:999px;}
.badge.sev{background:#fdecea;color:#c62828;}
.badge.reach{background:#eef4ee;color:#1b5e20;}
.badge.trend-rising{background:#fff4e0;color:#9a6b00;}
.badge.trend-new{background:#e7f0fb;color:#1d5fb0;}
.badge.trend-steady{background:#eef1ee;color:#5d6b5d;}
.badge.trend-cooling{background:#eef4ee;color:#1b5e20;}
.why{margin:8px 0;}
.issue{color:#5d6b5d;margin:6px 0 4px;}
.section-title{font-size:12px;text-transform:uppercase;letter-spacing:.05em;
  color:#5d6b5d;margin:16px 0 6px;}
ul.evidence{list-style:none;padding:0;margin:0;}
ul.evidence li{border-left:3px solid #e2e7e2;padding:7px 0 7px 13px;margin:8px 0;}
ul.evidence li.acute{border-left-color:#c62828;background:#fdecea;border-radius:0 8px 8px 0;padding-right:10px;}
.quote{font-style:italic;}
.who{display:block;color:#5d6b5d;font-size:13px;margin-top:3px;font-style:normal;}
.more{color:#5d6b5d;font-size:13px;margin-top:8px;}
.hitl{margin-top:14px;padding:11px 13px;background:#f6f8f6;border-radius:8px;font-size:13px;color:#41513f;}
.escalated{background:#fff;border:1px dashed #d7ddd7;border-radius:10px;padding:10px 16px;}
.escalated .e{padding:4px 0;}
footer.note{margin-top:28px;padding:16px 18px;background:#fffaf0;border:1px solid #f0e2c0;
  border-radius:10px;color:#7a5b00;font-size:14px;}
.empty{color:#5d6b5d;font-style:italic;}
"""


def _page(title: str, subtitle: str, meta_html: str, body: str) -> str:
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        f"<title>{_esc(title)}</title>\n<style>{_CSS}</style></head>\n"
        "<body><div class=\"wrap\">\n"
        f"<header class=\"page\"><h1>{_esc(title)}</h1>"
        f"<div class=\"sub\">{_esc(subtitle)}</div>{meta_html}</header>\n"
        f"{body}\n</div></body></html>\n"
    )


def _urgent_card(alert: dict) -> str:
    ev = alert["evidence"]
    items = []
    for e in ev[:4]:
        acute = e.get("acute")
        cls = ' class="acute"' if acute else ""
        tag = "<strong>[RETENTION RISK] </strong>" if acute else ""
        items.append(
            f'<li{cls}><span class="quote">{tag}&ldquo;{_esc(e["evidence_snippet"])}&rdquo;</span>'
            f'<span class="who">&mdash; {_esc(e["author_role"])}, {_esc(e["channel"])}</span></li>'
        )
    more = (f'<p class="more">+{len(ev) - 4} more signals behind access control</p>'
            if len(ev) > 4 else "")
    head = "Re-escalation (materially grown)" if alert.get("is_reescalation") \
        else "Urgent &mdash; same-day escalation"
    return (
        '<div class="card urgent">'
        f'<div class="badges"><span class="badge sev">Severity {alert["max_severity"]}/5</span>'
        f'<span class="badge reach">{alert["count"]} voice(s) this cycle</span></div>'
        f'<h2>{_esc(alert["label"])}</h2>'
        f'<p class="why"><strong>{head}.</strong> Why now: {_esc(alert["reason"])}</p>'
        f'<p class="issue">A cluster of branch leaders / brand ambassadors are voicing the '
        f'same unresolved friction around {_esc(alert["label"].lower())}. '
        f'(Aggregate &mdash; no individual is named.)</p>'
        '<div class="section-title">Evidence &mdash; raw detail behind access control</div>'
        f'<ul class="evidence">{"".join(items)}</ul>{more}'
        '<div class="hitl"><strong>Human-in-the-loop:</strong> this internal alert fired '
        'automatically. Any outreach to the leaders/ambassadors themselves waits on a human '
        'reviewer (review-before-act). Suggested owner: Grassroots Leadership (on-call).</div>'
        '</div>'
    )


def _digest_doc(trend_themes: list, escalated: list, window: str, count: int) -> str:
    cards = []
    if not trend_themes:
        cards.append('<p class="empty">No trend-tier themes this week.</p>')
    for i, t in enumerate(trend_themes, 1):
        sym, cls = _TREND_HTML.get(t.trend, ("&bull;", "trend-steady"))
        evs = "".join(
            f'<li><span class="quote">&ldquo;{_esc(e["snippet"])}&rdquo;</span>'
            f'<span class="who">&mdash; {_esc(e["author_role"])}, {_esc(e["channel"])}</span></li>'
            for e in t.evidence[:2]
        )
        cards.append(
            '<div class="card trend">'
            f'<div class="badges"><span class="badge {cls}">{sym} {_esc(t.trend)}</span>'
            f'<span class="badge reach">{t.count} voice(s)</span>'
            f'<span class="badge sev">Severity {t.max_severity}/5</span></div>'
            f'<h2>{i}. {_esc(t.label)}</h2>'
            f'<p class="issue">{_esc(t.underlying_issue)}</p>'
            '<div class="section-title">Evidence &mdash; raw detail behind access control</div>'
            f'<ul class="evidence">{evs}</ul></div>'
        )

    esc_block = ""
    if escalated:
        rows = "".join(
            f'<div class="e">&bull; <strong>{_esc(t.label)}</strong> &mdash; {t.count} signals, '
            f'severity {t.max_severity}/5 (urgent alert already fired)</div>'
            for t in escalated
        )
        esc_block = ('<div class="section-title">Already escalated this week '
                     '(for context &mdash; see urgent alerts)</div>'
                     f'<div class="escalated">{rows}</div>')

    meta = (f'<div class="meta">Window: {_esc(window)} &nbsp;&middot;&nbsp; Sources: Zoom/Fathom '
            f'debriefs + public role inboxes (questions@ / talkback@ / volunteer@) '
            f'&nbsp;&middot;&nbsp; New pain-point signals this week: {count}</div>')
    return _page(
        "ACC Voices — Weekly Improvement Digest",
        "Steady improvement, not emergencies — ranked by a blended severity + frequency + trend signal.",
        meta, "".join(cards) + esc_block)
