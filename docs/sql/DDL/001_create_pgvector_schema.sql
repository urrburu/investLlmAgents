-- PostgreSQL DDL for the Invest LLM Agents canonical store.
--
-- Assumptions:
-- - This base schema does not require pgvector to be installed.
-- - If pgvector is available, run 002_enable_pgvector.sql after this file to
--   add chunks.embedding vector(1536) and the cosine HNSW index.
-- - Stable text IDs are application-facing identifiers used in citations,
--   logs, and LangGraph state. UUID columns are internal row identifiers.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS source_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id text NOT NULL UNIQUE,
    document_type text NOT NULL,
    title text NOT NULL,
    author_or_source text,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    raw_location text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT source_documents_document_type_check CHECK (
        document_type IN ('book', 'journal', 'report', 'memo', 'news', 'filing')
    ),
    CONSTRAINT source_documents_metadata_object_check CHECK (
        jsonb_typeof(metadata) = 'object'
    )
);

CREATE TABLE IF NOT EXISTS chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id text NOT NULL UNIQUE,
    document_id text NOT NULL REFERENCES source_documents(document_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    chunk_index integer NOT NULL,
    text text NOT NULL,
    page_or_offset text,
    embedding_id text,
    embedding_model text,
    embedding_dimensions integer,
    citation_label text,
    token_count integer,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chunks_chunk_index_nonnegative_check CHECK (chunk_index >= 0),
    CONSTRAINT chunks_text_nonempty_check CHECK (length(btrim(text)) > 0),
    CONSTRAINT chunks_token_count_nonnegative_check CHECK (
        token_count IS NULL OR token_count >= 0
    ),
    CONSTRAINT chunks_embedding_dimensions_positive_check CHECK (
        embedding_dimensions IS NULL OR embedding_dimensions > 0
    ),
    CONSTRAINT chunks_metadata_object_check CHECK (jsonb_typeof(metadata) = 'object'),
    CONSTRAINT chunks_document_index_unique UNIQUE (document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS wiki_pages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    page_id text NOT NULL UNIQUE,
    namespace text NOT NULL,
    page_type text NOT NULL,
    title text NOT NULL,
    body text NOT NULL DEFAULT '',
    source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    confidence text NOT NULL,
    open_questions jsonb NOT NULL DEFAULT '[]'::jsonb,
    current_revision_id text,
    last_reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT wiki_pages_page_type_check CHECK (
        page_type IN (
            'principle',
            'trade_pattern',
            'asset',
            'portfolio',
            'rule',
            'market_regime'
        )
    ),
    CONSTRAINT wiki_pages_confidence_check CHECK (
        confidence IN ('high', 'medium', 'low')
    ),
    CONSTRAINT wiki_pages_source_refs_array_check CHECK (
        jsonb_typeof(source_refs) = 'array'
    ),
    CONSTRAINT wiki_pages_open_questions_array_check CHECK (
        jsonb_typeof(open_questions) = 'array'
    )
);

CREATE TABLE IF NOT EXISTS wiki_revisions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    revision_id text NOT NULL UNIQUE,
    page_id text NOT NULL REFERENCES wiki_pages(page_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    operation text NOT NULL,
    change_summary text NOT NULL,
    before_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    after_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    diff_summary text NOT NULL,
    proposed_body text NOT NULL,
    source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    verification_result_id text,
    status text NOT NULL DEFAULT 'draft',
    review_actions jsonb NOT NULL DEFAULT '[]'::jsonb,
    requested_changes jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_by_agent text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT wiki_revisions_operation_check CHECK (
        operation IN ('create', 'update', 'merge', 'split')
    ),
    CONSTRAINT wiki_revisions_status_check CHECK (
        status IN ('draft', 'verified', 'needs_human_review', 'rejected', 'accepted')
    ),
    CONSTRAINT wiki_revisions_before_refs_array_check CHECK (
        jsonb_typeof(before_refs) = 'array'
    ),
    CONSTRAINT wiki_revisions_after_refs_array_check CHECK (
        jsonb_typeof(after_refs) = 'array'
    ),
    CONSTRAINT wiki_revisions_source_refs_array_check CHECK (
        jsonb_typeof(source_refs) = 'array'
    ),
    CONSTRAINT wiki_revisions_review_actions_array_check CHECK (
        jsonb_typeof(review_actions) = 'array'
    ),
    CONSTRAINT wiki_revisions_requested_changes_array_check CHECK (
        jsonb_typeof(requested_changes) = 'array'
    )
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id text NOT NULL UNIQUE,
    as_of timestamptz NOT NULL,
    base_currency text NOT NULL,
    cash numeric(28, 8) NOT NULL DEFAULT 0,
    source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT portfolio_snapshots_cash_nonnegative_check CHECK (cash >= 0),
    CONSTRAINT portfolio_snapshots_source_refs_array_check CHECK (
        jsonb_typeof(source_refs) = 'array'
    ),
    CONSTRAINT portfolio_snapshots_metadata_object_check CHECK (
        jsonb_typeof(metadata) = 'object'
    )
);

CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id text NOT NULL REFERENCES portfolio_snapshots(snapshot_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    ticker text NOT NULL,
    name text,
    quantity numeric(28, 8) NOT NULL,
    cost_basis numeric(28, 8),
    market_price numeric(28, 8),
    market_value numeric(28, 8),
    weight numeric(20, 10),
    sector text,
    data_status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT portfolio_holdings_weight_bounds_check CHECK (
        weight IS NULL OR (weight >= 0 AND weight <= 1)
    ),
    CONSTRAINT portfolio_holdings_data_status_check CHECK (
        data_status IN ('complete', 'partial', 'missing_price', 'missing_cost')
    ),
    CONSTRAINT portfolio_holdings_snapshot_ticker_unique UNIQUE (snapshot_id, ticker)
);

CREATE TABLE IF NOT EXISTS report_drafts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id text NOT NULL UNIQUE,
    report_type text NOT NULL,
    title text NOT NULL,
    as_of timestamptz,
    sections jsonb NOT NULL DEFAULT '[]'::jsonb,
    claims jsonb NOT NULL DEFAULT '[]'::jsonb,
    numbers jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    actions jsonb NOT NULL DEFAULT '[]'::jsonb,
    verification_status text NOT NULL DEFAULT 'pending',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT report_drafts_report_type_check CHECK (
        report_type IN (
            'daily_check',
            'weekly_review',
            'stock_snapshot',
            'portfolio_report',
            'market_brief'
        )
    ),
    CONSTRAINT report_drafts_verification_status_check CHECK (
        verification_status IN (
            'pending',
            'passed',
            'needs_revision',
            'needs_human_review',
            'blocked'
        )
    ),
    CONSTRAINT report_drafts_sections_array_check CHECK (
        jsonb_typeof(sections) = 'array'
    ),
    CONSTRAINT report_drafts_claims_array_check CHECK (
        jsonb_typeof(claims) = 'array'
    ),
    CONSTRAINT report_drafts_numbers_array_check CHECK (
        jsonb_typeof(numbers) = 'array'
    ),
    CONSTRAINT report_drafts_source_refs_array_check CHECK (
        jsonb_typeof(source_refs) = 'array'
    ),
    CONSTRAINT report_drafts_actions_array_check CHECK (
        jsonb_typeof(actions) = 'array'
    )
);

CREATE TABLE IF NOT EXISTS verification_results (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    verification_result_id text NOT NULL UNIQUE,
    target_id text NOT NULL,
    target_type text,
    status text NOT NULL,
    number_checks jsonb NOT NULL DEFAULT '[]'::jsonb,
    citation_checks jsonb NOT NULL DEFAULT '[]'::jsonb,
    language_checks jsonb NOT NULL DEFAULT '[]'::jsonb,
    staleness_checks jsonb NOT NULL DEFAULT '[]'::jsonb,
    required_fixes jsonb NOT NULL DEFAULT '[]'::jsonb,
    required_inputs jsonb NOT NULL DEFAULT '[]'::jsonb,
    safe_sections jsonb NOT NULL DEFAULT '[]'::jsonb,
    hidden_sections jsonb NOT NULL DEFAULT '[]'::jsonb,
    quality_score integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT verification_results_target_type_check CHECK (
        target_type IS NULL OR target_type IN ('report_draft', 'wiki_revision')
    ),
    CONSTRAINT verification_results_status_check CHECK (
        status IN (
            'pending',
            'passed',
            'needs_revision',
            'needs_human_review',
            'blocked'
        )
    ),
    CONSTRAINT verification_results_quality_score_bounds_check CHECK (
        quality_score >= 0 AND quality_score <= 100
    ),
    CONSTRAINT verification_results_number_checks_array_check CHECK (
        jsonb_typeof(number_checks) = 'array'
    ),
    CONSTRAINT verification_results_citation_checks_array_check CHECK (
        jsonb_typeof(citation_checks) = 'array'
    ),
    CONSTRAINT verification_results_language_checks_array_check CHECK (
        jsonb_typeof(language_checks) = 'array'
    ),
    CONSTRAINT verification_results_staleness_checks_array_check CHECK (
        jsonb_typeof(staleness_checks) = 'array'
    ),
    CONSTRAINT verification_results_required_fixes_array_check CHECK (
        jsonb_typeof(required_fixes) = 'array'
    ),
    CONSTRAINT verification_results_required_inputs_array_check CHECK (
        jsonb_typeof(required_inputs) = 'array'
    ),
    CONSTRAINT verification_results_safe_sections_array_check CHECK (
        jsonb_typeof(safe_sections) = 'array'
    ),
    CONSTRAINT verification_results_hidden_sections_array_check CHECK (
        jsonb_typeof(hidden_sections) = 'array'
    )
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id text NOT NULL UNIQUE,
    agent_name text NOT NULL,
    trigger_type text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    current_node text,
    last_event_at timestamptz,
    progress_label text,
    status text NOT NULL DEFAULT 'running',
    input_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    intermediate_artifacts jsonb NOT NULL DEFAULT '[]'::jsonb,
    report_id text REFERENCES report_drafts(report_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    revision_id text REFERENCES wiki_revisions(revision_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    verification_result_id text REFERENCES verification_results(verification_result_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    verification_status text NOT NULL DEFAULT 'pending',
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
    missing_inputs jsonb NOT NULL DEFAULT '[]'::jsonb,
    blocked_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
    artifact_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT agent_runs_trigger_type_check CHECK (
        trigger_type IN ('manual', 'schedule', 'upload', 'follow_up')
    ),
    CONSTRAINT agent_runs_status_check CHECK (
        status IN ('running', 'completed', 'needs_human_review', 'blocked', 'failed')
    ),
    CONSTRAINT agent_runs_verification_status_check CHECK (
        verification_status IN (
            'pending',
            'passed',
            'needs_revision',
            'needs_human_review',
            'blocked'
        )
    ),
    CONSTRAINT agent_runs_input_refs_array_check CHECK (
        jsonb_typeof(input_refs) = 'array'
    ),
    CONSTRAINT agent_runs_intermediate_artifacts_array_check CHECK (
        jsonb_typeof(intermediate_artifacts) = 'array'
    ),
    CONSTRAINT agent_runs_warnings_array_check CHECK (
        jsonb_typeof(warnings) = 'array'
    ),
    CONSTRAINT agent_runs_missing_inputs_array_check CHECK (
        jsonb_typeof(missing_inputs) = 'array'
    ),
    CONSTRAINT agent_runs_blocked_reasons_array_check CHECK (
        jsonb_typeof(blocked_reasons) = 'array'
    ),
    CONSTRAINT agent_runs_artifact_ids_array_check CHECK (
        jsonb_typeof(artifact_ids) = 'array'
    )
);

CREATE TABLE IF NOT EXISTS agent_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type text NOT NULL,
    run_id text NOT NULL REFERENCES agent_runs(run_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT agent_events_event_type_check CHECK (
        event_type IN (
            'agent_run_started',
            'external_data_fetched',
            'verification_failed',
            'report_blocked',
            'revision_proposed',
            'agent_run_completed'
        )
    ),
    CONSTRAINT agent_events_payload_object_check CHECK (
        jsonb_typeof(payload) = 'object'
    )
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'wiki_pages_current_revision_fk'
          AND conrelid = 'wiki_pages'::regclass
    ) THEN
        ALTER TABLE wiki_pages
            ADD CONSTRAINT wiki_pages_current_revision_fk
            FOREIGN KEY (current_revision_id)
            REFERENCES wiki_revisions(revision_id)
            ON UPDATE CASCADE
            ON DELETE SET NULL;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'wiki_revisions_verification_result_fk'
          AND conrelid = 'wiki_revisions'::regclass
    ) THEN
        ALTER TABLE wiki_revisions
            ADD CONSTRAINT wiki_revisions_verification_result_fk
            FOREIGN KEY (verification_result_id)
            REFERENCES verification_results(verification_result_id)
            ON UPDATE CASCADE
            ON DELETE SET NULL;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS source_documents_document_type_idx
    ON source_documents (document_type);
CREATE INDEX IF NOT EXISTS source_documents_published_at_idx
    ON source_documents (published_at);
CREATE INDEX IF NOT EXISTS source_documents_metadata_gin_idx
    ON source_documents USING gin (metadata);

CREATE INDEX IF NOT EXISTS chunks_document_id_idx
    ON chunks (document_id);
CREATE INDEX IF NOT EXISTS chunks_embedding_id_idx
    ON chunks (embedding_id)
    WHERE embedding_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS chunks_metadata_gin_idx
    ON chunks USING gin (metadata);
CREATE INDEX IF NOT EXISTS chunks_text_search_idx
    ON chunks USING gin (to_tsvector('simple', text));

CREATE INDEX IF NOT EXISTS wiki_pages_namespace_idx
    ON wiki_pages (namespace);
CREATE INDEX IF NOT EXISTS wiki_pages_page_type_idx
    ON wiki_pages (page_type);
CREATE INDEX IF NOT EXISTS wiki_pages_source_refs_gin_idx
    ON wiki_pages USING gin (source_refs);

CREATE INDEX IF NOT EXISTS wiki_revisions_page_id_idx
    ON wiki_revisions (page_id);
CREATE INDEX IF NOT EXISTS wiki_revisions_status_idx
    ON wiki_revisions (status);
CREATE INDEX IF NOT EXISTS wiki_revisions_source_refs_gin_idx
    ON wiki_revisions USING gin (source_refs);

CREATE INDEX IF NOT EXISTS portfolio_snapshots_as_of_idx
    ON portfolio_snapshots (as_of DESC);
CREATE INDEX IF NOT EXISTS portfolio_holdings_snapshot_id_idx
    ON portfolio_holdings (snapshot_id);
CREATE INDEX IF NOT EXISTS portfolio_holdings_ticker_idx
    ON portfolio_holdings (ticker);

CREATE INDEX IF NOT EXISTS report_drafts_report_type_idx
    ON report_drafts (report_type);
CREATE INDEX IF NOT EXISTS report_drafts_verification_status_idx
    ON report_drafts (verification_status);
CREATE INDEX IF NOT EXISTS report_drafts_as_of_idx
    ON report_drafts (as_of DESC);

CREATE INDEX IF NOT EXISTS verification_results_target_idx
    ON verification_results (target_id, target_type);
CREATE INDEX IF NOT EXISTS verification_results_status_idx
    ON verification_results (status);

CREATE INDEX IF NOT EXISTS agent_runs_status_idx
    ON agent_runs (status);
CREATE INDEX IF NOT EXISTS agent_runs_started_at_idx
    ON agent_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS agent_runs_current_node_idx
    ON agent_runs (current_node)
    WHERE current_node IS NOT NULL;
CREATE INDEX IF NOT EXISTS agent_events_run_created_idx
    ON agent_events (run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS agent_events_event_type_idx
    ON agent_events (event_type);
CREATE INDEX IF NOT EXISTS agent_events_payload_gin_idx
    ON agent_events USING gin (payload);

DO $$
DECLARE
    table_name text;
    trigger_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'source_documents',
        'chunks',
        'wiki_pages',
        'wiki_revisions',
        'portfolio_snapshots',
        'portfolio_holdings',
        'report_drafts',
        'verification_results',
        'agent_runs'
    ]
    LOOP
        trigger_name := table_name || '_set_updated_at';

        IF NOT EXISTS (
            SELECT 1
            FROM pg_trigger
            WHERE tgname = trigger_name
              AND tgrelid = to_regclass(table_name)
        ) THEN
            EXECUTE format(
                'CREATE TRIGGER %I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION set_updated_at()',
                trigger_name,
                table_name
            );
        END IF;
    END LOOP;
END;
$$;

COMMIT;
