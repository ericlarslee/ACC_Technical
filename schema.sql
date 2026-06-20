-- ============================================================================
-- ACC Voices — PostgreSQL data model (authoritative DDL)
--
-- This is the production schema. The demo keeps the same shapes in an in-memory
-- stub (see pipeline/store.py) so it needs no database; this file is what you
-- would actually `psql -f schema.sql` against Postgres in production.
--
-- Design decision #4 (data minimization) is encoded structurally: there is NO
-- raw-body column anywhere. We keep extracted structured signals + a short
-- evidence snippet + a pointer back to the source. Transcripts and full email
-- bodies are never warehoused — privacy control and cost/volume control at once.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Per-source cursor / watermark. Backs incremental, idempotent polling: each
-- adapter pulls only what is newer than its stored watermark on every run.
-- ---------------------------------------------------------------------------
CREATE TABLE source_cursor (
    source_name   TEXT        PRIMARY KEY,          -- e.g. 'fathom_transcripts'
    watermark     TEXT        NOT NULL,             -- last occurred_at / id processed
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Canonical communication record (Canonical Data Model). One row per ingested
-- signal, regardless of source. NO body column, by design.
-- ---------------------------------------------------------------------------
CREATE TABLE communication_record (
    record_id      TEXT        PRIMARY KEY,
    source_type    TEXT        NOT NULL CHECK (source_type IN ('transcript','email','form','slack')),
    source_adapter TEXT        NOT NULL,            -- which adapter produced it
    source_ref     TEXT        NOT NULL,            -- provenance pointer to the source system
    channel        TEXT        NOT NULL,            -- public role inbox / targeted-call title
    author_role    TEXT        NOT NULL CHECK (author_role IN ('branch_leader','brand_ambassador','unknown')),
    occurred_at    TIMESTAMPTZ NOT NULL,
    consent_basis  TEXT        NOT NULL,            -- WHY we may analyze this signal
    metadata       JSONB       NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX idx_record_occurred ON communication_record (occurred_at);
CREATE INDEX idx_record_source   ON communication_record (source_type);

-- ---------------------------------------------------------------------------
-- Extracted pain-point candidate. One row per pain point Claude found in a
-- record (most records produce zero). Carries the grade the router keys on and
-- a short evidence snippet (not the full body).
-- ---------------------------------------------------------------------------
CREATE TABLE pain_point_candidate (
    candidate_id     TEXT        PRIMARY KEY,
    record_id        TEXT        NOT NULL REFERENCES communication_record(record_id),
    category         TEXT        NOT NULL,
    issue_text       TEXT        NOT NULL,          -- generalized statement of the friction
    severity         SMALLINT    NOT NULL CHECK (severity BETWEEN 1 AND 5),
    urgency          SMALLINT    NOT NULL CHECK (urgency  BETWEEN 1 AND 5),
    evidence_snippet TEXT        NOT NULL,          -- short verbatim quote only
    confidence       REAL        NOT NULL,
    acute            BOOLEAN     NOT NULL DEFAULT false,  -- attrition / "about to walk" signal
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_candidate_category ON pain_point_candidate (category);
CREATE INDEX idx_candidate_record   ON pain_point_candidate (record_id);

-- ---------------------------------------------------------------------------
-- Theme / cluster. One row per recurring theme produced by the weekly Claude
-- clustering pass. `count` is the dedup'd frequency (issue raised 5x => count 5).
-- ---------------------------------------------------------------------------
CREATE TABLE theme (
    theme_key        TEXT        PRIMARY KEY,        -- e.g. 'reimbursement:weekly'
    label            TEXT        NOT NULL,
    category         TEXT        NOT NULL,
    count            INTEGER     NOT NULL,
    underlying_issue TEXT        NOT NULL,
    max_severity     SMALLINT    NOT NULL,
    max_urgency      SMALLINT    NOT NULL,
    trend            TEXT        NOT NULL CHECK (trend IN ('rising','steady','new','cooling')),
    tier             TEXT        CHECK (tier IN ('urgent','trend')),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Evidence link. Ties each theme back to the candidates / source records and
-- snippets behind it — full lineage so leadership can trust and verify a theme.
-- ---------------------------------------------------------------------------
CREATE TABLE theme_evidence (
    id           BIGSERIAL PRIMARY KEY,
    theme_key    TEXT NOT NULL REFERENCES theme(theme_key) ON DELETE CASCADE,
    candidate_id TEXT NOT NULL REFERENCES pain_point_candidate(candidate_id),
    record_id    TEXT NOT NULL REFERENCES communication_record(record_id),
    snippet      TEXT NOT NULL
);
CREATE INDEX idx_evidence_theme ON theme_evidence (theme_key);

-- ---------------------------------------------------------------------------
-- Alert state. Backs the dedup that makes escalation idempotent: once an urgent
-- alert fires for a theme it is remembered, and a later run only re-fires if the
-- cluster has materially grown. This is the primary defense against alarm fatigue
-- and matters even more under polling than under streaming.
-- ---------------------------------------------------------------------------
CREATE TABLE alert_state (
    theme_key        TEXT        PRIMARY KEY,        -- e.g. 'reimbursement:urgent'
    tier             TEXT        NOT NULL,
    status           TEXT        NOT NULL CHECK (status IN ('active','resolved')),
    last_count       INTEGER     NOT NULL,
    last_severity    SMALLINT    NOT NULL,
    first_alerted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_alerted_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
