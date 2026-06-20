"""Triage & routing — the heart of the system.

A Content-Based Router, implemented as a function invoked at the END of each
ingest-triage run (NOT a stream consumer). It keys on the severity/urgency grade
to send each pain-point theme down the urgent path or the trend path, and it
maintains per-theme alert state so an already-escalated issue is not re-alerted
on every subsequent run — the primary defense against alarm fatigue.
"""
