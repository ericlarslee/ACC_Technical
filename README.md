# ACC Voices — surfacing branch-leader & ambassador pain points (Scenario C)

A scheduled batch pipeline that reads ACC's existing communications with branch
leaders and brand ambassadors, pulls out the recurring human friction (slow
reimbursement, feeling unsupported at events, unclear comms from national,
onboarding confusion, burnout), and routes it to grassroots leadership two ways:
a same-day alert for anything urgent, and a weekly digest for the slow-burn stuff.

This is the one-hour exercise version: the analysis logic is real, but every
external system (Zoom/Fathom, Gmail) is stubbed behind its adapter so the demo
runs over canned data.

## Run it

```bash
cd ScenarioC
python3 run_demo.py
```

Standard library only — no install, no API key. It runs the full pipeline over the
sample data and writes two HTML artifacts — the urgent alert and the weekly digest
— to `sample-reports/stubbed/`. To run against real Claude instead of the offline
mock: `pip install anthropic`, then `export ANTHROPIC_API_KEY=... ACC_USE_REAL_CLAUDE=1`;
those runs write to `sample-reports/real-claude/`. (Committed stubbed reports are
included; the real-claude folder fills when you run with a key.)

## How it works

```
SOURCES  (real systems — stubbed in this build)
  Zoom / Fathom transcripts (targeted calls)  |  Gmail role inboxes (questions@/talkback@/volunteer@)
  Google Forms (future)                       |  Slack (future)
                          |
                          v
INGESTION  —  Source Adapter (Strategy) + Canonical Data Model
  TranscriptAdapter . EmailAdapter . FormsAdapter* . SlackAdapter*
  config-driven registry . per-source cursor/watermark (incremental, idempotent)
                          |  each adapter emits ONE CommunicationRecord
                          v
ANALYSIS  —  Pipes-and-Filters   (Claude is the only model)
  Filter 1  EXTRACT   (Claude prompt #1, per record)  ->  graded pain-point candidates
  Filter 2  CLUSTER   (Claude prompt #2, once/batch)  ->  deduped themes + provenance
                          |
                          v
TRIAGE  —  Content-Based Router   (keys on the severity/urgency grade + velocity)
  + alert_state   (idempotent; primary defense against alarm fatigue)
                          |
               +----------+-----------+
         urgent|                      |trend  (accumulate for the weekly digest)
               v                      v
SURFACING  —  Tiered Notification   (+ human-in-the-loop gate before any outward action)
  URGENT alert (Slack/email, same-day)        WEEKLY digest (trend themes)

PostgreSQL persists:  communication_record . pain_point_candidate . theme . theme_evidence . alert_state

Scheduled entry points (cron — NOT an always-on service):
  JOB 1 (frequent):  ingest -> extract -> grade -> route    (fires urgent alerts at end of run)
  JOB 2 (weekly):    aggregate -> cluster -> digest
```

Four layers, each a recognizable pattern:

- **Ingestion** — a Source Adapter (Strategy) per source, all emitting one
  canonical `CommunicationRecord`. A config-driven registry decides what's active;
  each adapter polls incrementally against a stored cursor so reruns are
  idempotent. Email is restricted to public role inboxes by a hard allowlist;
  transcripts are only the targeted debrief / leader calls, not every meeting.
- **Analysis** — a two-stage Pipes-and-Filters flow; Claude is the only model.
  Extraction runs per record (structured JSON: is there friction, how
  severe/urgent, a short quote). Clustering runs once over the batch (group into
  themes and dedup — the same issue raised five times becomes one theme, count 5).
- **Triage** — a Content-Based Router invoked at the end of each run. It keys on
  the grade plus how fast a theme is spreading and routes each theme urgent or
  trend. `alert_state` makes escalation idempotent, so the same fire isn't
  re-alerted on every run.
- **Surfacing** — the two artifacts leadership receives. Themes are aggregate
  ("five leaders flagged reimbursement"), never named individuals, with raw
  evidence behind access control; an internal alert never triggers outward action
  on its own — a human reviews first.

## Data model

PostgreSQL — full DDL in `schema.sql`. Notably, `communication_record` stores **no
raw body**: only the extracted signals, a short evidence quote, and a pointer back
to the source. `theme_evidence` keeps the lineage from a theme back to its source
records; `alert_state` backs the dedup; `source_cursor` holds the per-source
watermarks. The demo runs against an in-memory stub of these tables (no database
needed); production swaps in a Postgres-backed store behind the same interface.

## Decisions worth calling out

- **Consent by design.** Only public, monitored role inboxes — never personal
  mail. Those addresses carry a standing "messages here are reviewed to help us
  support our leaders and ambassadors" notice, recorded as the consent basis on
  every record.
- **Data minimization.** We never warehouse transcripts or email bodies, just the
  extracted signal + a short quote + a source pointer. Privacy control and cost
  control at once.
- **Two failure modes.** Over-surfacing (alarm fatigue) is handled with severity
  thresholds, dedup, and `alert_state`. Under-surfacing — the leader who's unhappy
  and simply goes quiet — is the harder one and this system can't catch it on its
  own; the planned fix is coverage tracking (below).
- **Model choice is tunable.** Extraction and clustering models are env-overridable
  (`ACC_EXTRACT_MODEL` / `ACC_CLUSTER_MODEL`, both default to Sonnet). It's worth
  monitoring grade quality against real data and adjusting, not setting once.

## Batch, not a service

Two cron jobs (`cron/crontab.example`): a frequent ingest-extract-triage run that
fires urgent alerts, and a weekly aggregate-and-digest run. No webhooks or queues
— the volume is low and the urgent SLA is same-day, so polling is enough and
urgent latency just equals the cron interval.

## Future work (not built)

Communication-coverage tracking: measure which leaders/ambassadors we've actually
heard from lately against the Monday.com roster, and flag anyone who's gone quiet.
That's the structural fix for the silent-disengagement half of under-surfacing.
Additional sources (Google Forms, Slack) plug into the same adapter interface —
already stubbed.
