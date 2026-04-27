-- app/storage/schema.sql
-- Bootstrap schema for the daily AI investment pipeline.
--
-- Design constraints:
--   - All tables use CREATE TABLE IF NOT EXISTS (idempotent).
--   - All indexes use CREATE INDEX IF NOT EXISTS (idempotent).
--   - Foreign key enforcement is enabled by the connection helper.
--   - ISO-8601 UTC strings are used for all timestamps (TEXT columns).
--   - url_fingerprint and content_hash support URL/text dedup in later phases.
--   - run_logs.batch_index supports same-day multi-batch runs (08:30 + 14:00).
--
-- Tables defined here (bootstrap level only — no collector or analysis logic):
--   run_logs        : per-batch run metadata and status
--   raw_documents   : raw crawl results from all adapters
--   news_items      : normalised / standardised news records
--   entities        : companies, products, technologies, supply-chain nodes
--   news_entity_links : M:N between news_items and entities
--   info_chains     : information chains (causal / temporal / upstream-downstream)
--   chain_evidence  : evidence items linking news_items to info_chains
--   chain_scores    : novelty / importance / credibility / A-share relevance scores

-- ---------------------------------------------------------------------------
-- run_logs — one row per batch execution
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS run_logs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date            TEXT    NOT NULL,           -- YYYY-MM-DD
    batch_index         INTEGER NOT NULL DEFAULT 0, -- 0-based; supports 08:30 + 14:00 batches
    started_at          TEXT    NOT NULL,           -- ISO-8601 UTC
    finished_at         TEXT,                       -- NULL while running
    status              TEXT    NOT NULL DEFAULT 'running',  -- running / success / failed
    error_text          TEXT,
    prompt_profile_name TEXT    NOT NULL DEFAULT 'default',
    prompt_profile_version TEXT  NOT NULL DEFAULT 'unknown',
    prompt_profile_desc TEXT     -- full profile description
);

CREATE INDEX IF NOT EXISTS idx_run_logs_run_date
    ON run_logs (run_date);

CREATE INDEX IF NOT EXISTS idx_run_logs_status
    ON run_logs (status);

-- ---------------------------------------------------------------------------
-- raw_documents — raw crawl output from all source adapters
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER REFERENCES run_logs(id),
    source          TEXT    NOT NULL,           -- akshare / web / copilot_research
    url             TEXT    NOT NULL,
    url_fingerprint TEXT    UNIQUE,             -- normalised URL hash for dedup
    fetched_at      TEXT    NOT NULL,           -- ISO-8601 UTC
    http_status     INTEGER,
    content_hash    TEXT,                       -- SHA-256 of raw_content for text dedup
    raw_content     TEXT,
    fetch_error     TEXT                        -- non-NULL if fetch failed
);

CREATE INDEX IF NOT EXISTS idx_raw_documents_url_fingerprint
    ON raw_documents (url_fingerprint);

CREATE INDEX IF NOT EXISTS idx_raw_documents_content_hash
    ON raw_documents (content_hash);

CREATE INDEX IF NOT EXISTS idx_raw_documents_run_id
    ON raw_documents (run_id);

CREATE INDEX IF NOT EXISTS idx_raw_documents_source_fetched
    ON raw_documents (source, fetched_at);

-- ---------------------------------------------------------------------------
-- news_items — normalised / standardised records
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS news_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_document_id     INTEGER REFERENCES raw_documents(id),
    run_id              INTEGER REFERENCES run_logs(id),
    title               TEXT,
    body                TEXT,
    published_at        TEXT,                   -- ISO-8601 UTC (NULL if unknown)
    source_url          TEXT,
    source_name         TEXT,
    source_credibility  INTEGER DEFAULT 0,      -- 0=unknown 1=low … 5=high
    content_hash        TEXT,                   -- SHA-256 of (title+body) for dedup
    created_at          TEXT    NOT NULL        -- ISO-8601 UTC, set on insert
);

CREATE INDEX IF NOT EXISTS idx_news_items_content_hash
    ON news_items (content_hash);

CREATE INDEX IF NOT EXISTS idx_news_items_published_at
    ON news_items (published_at);

CREATE INDEX IF NOT EXISTS idx_news_items_run_id
    ON news_items (run_id);

-- ---------------------------------------------------------------------------
-- entities — companies, products, technologies, supply-chain roles
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    entity_type TEXT    NOT NULL DEFAULT 'unknown',
                                            -- company / product / technology /
                                            -- supply_chain / region / policy / unknown
    aliases     TEXT    DEFAULT '[]',       -- JSON array of alternate names
    created_at  TEXT    NOT NULL            -- ISO-8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_entities_name
    ON entities (name);

CREATE INDEX IF NOT EXISTS idx_entities_type
    ON entities (entity_type);

-- ---------------------------------------------------------------------------
-- news_entity_links — M:N junction between news_items and entities
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS news_entity_links (
    news_item_id    INTEGER NOT NULL REFERENCES news_items(id),
    entity_id       INTEGER NOT NULL REFERENCES entities(id),
    PRIMARY KEY (news_item_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_nel_entity_id
    ON news_entity_links (entity_id);

-- ---------------------------------------------------------------------------
-- info_chains — information chains connecting discrete events
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS info_chains (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER REFERENCES run_logs(id),
    title       TEXT,
    summary     TEXT,
    chain_type  TEXT    NOT NULL DEFAULT 'unknown',
                                            -- causal / temporal / upstream_downstream / unknown
    created_at  TEXT    NOT NULL            -- ISO-8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_info_chains_run_id
    ON info_chains (run_id);

CREATE INDEX IF NOT EXISTS idx_info_chains_created_at
    ON info_chains (created_at);

-- ---------------------------------------------------------------------------
-- chain_evidence — evidence items linking news_items to info_chains
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chain_evidence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id        INTEGER NOT NULL REFERENCES info_chains(id),
    news_item_id    INTEGER NOT NULL REFERENCES news_items(id),
    relevance_score REAL    DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_chain_evidence_chain_id
    ON chain_evidence (chain_id);

CREATE INDEX IF NOT EXISTS idx_chain_evidence_news_item_id
    ON chain_evidence (news_item_id);

-- ---------------------------------------------------------------------------
-- chain_scores — multi-dimensional scoring output for each info chain
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chain_scores (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id                INTEGER NOT NULL REFERENCES info_chains(id),
    run_id                  INTEGER REFERENCES run_logs(id),
    novelty                 REAL    DEFAULT 0.0,    -- 0.0–1.0
    importance              REAL    DEFAULT 0.0,    -- 0.0–1.0
    credibility             REAL    DEFAULT 0.0,    -- 0.0–1.0
    a_share_relevance       REAL    DEFAULT 0.0,    -- 0.0–1.0; A-share mapping weight
    overall                 REAL    DEFAULT 0.0,    -- composite score
    scored_at               TEXT    NOT NULL,       -- ISO-8601 UTC
    prompt_profile_name     TEXT    NOT NULL DEFAULT 'default',
    prompt_profile_version  TEXT    NOT NULL DEFAULT 'unknown'
);

CREATE INDEX IF NOT EXISTS idx_chain_scores_chain_id
    ON chain_scores (chain_id);

CREATE INDEX IF NOT EXISTS idx_chain_scores_run_id
    ON chain_scores (run_id);

CREATE INDEX IF NOT EXISTS idx_chain_scores_overall
    ON chain_scores (overall DESC);

-- ---------------------------------------------------------------------------
-- prompt_profiles — archived prompt profiles for reproducibility
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prompt_profiles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_name    TEXT    NOT NULL,
    version         TEXT    NOT NULL,
    description     TEXT,
    config_json     TEXT    NOT NULL,  -- full YAML config converted to JSON
    template_files  TEXT    NOT NULL,  -- JSON map of task_type to template content
    archived_at     TEXT    NOT NULL,  -- ISO-8601 UTC when this profile was archived
    UNIQUE(profile_name, version)
);

CREATE INDEX IF NOT EXISTS idx_prompt_profiles_name_version
    ON prompt_profiles (profile_name, version);
