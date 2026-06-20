"""ACC Voices — passive pain-point surfacing pipeline.

A scheduled, batch analytical pipeline (NOT a stream processor / always-on
service) that listens to ACC's member communications and surfaces the lived,
human friction branch leaders and brand ambassadors hit day-to-day.

Layers (each implemented with a named, recognizable pattern):
  - adapters/   Source Adapter (Strategy) + Canonical Data Model + source registry
  - analysis/   Pipes-and-Filters: Claude extraction per record, then one Claude
                clustering pass over the batch (Claude is the ONLY model)
  - triage/     Content-Based Router keyed on the severity/urgency grade, with
                per-theme alert-state for idempotent, fatigue-resistant alerting
  - surfacing/  Tiered notification: same-day urgent alert + weekly trend digest,
                with a human-in-the-loop gate before anything outward-facing
"""
