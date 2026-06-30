"""PostgreSQL storage helpers used by write_internal skills."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from invest_llm_agents.skills.base import to_jsonable


DATABASE_URL_ENV = "INVEST_LLM_DATABASE_URL"
DB_HOST_ENV = "INVEST_LLM_DB_HOST"
DB_PORT_ENV = "INVEST_LLM_DB_PORT"
DB_NAME_ENV = "INVEST_LLM_DB_NAME"
DB_USER_ENV = "INVEST_LLM_DB_USER"
DB_PASSWORD_ENV = "INVEST_LLM_DB_PASSWORD"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            values[key] = value
    return values


def local_env_values() -> dict[str, str]:
    root = repo_root()
    values = parse_env_file(root / ".env")
    values.update(parse_env_file(root / ".env.local"))
    return values


def env_value(name: str) -> str | None:
    return os.getenv(name) or local_env_values().get(name)


def database_url_from_env() -> str | None:
    database_url = env_value(DATABASE_URL_ENV)
    if database_url:
        return database_url

    host = env_value(DB_HOST_ENV)
    database = env_value(DB_NAME_ENV)
    user = env_value(DB_USER_ENV)
    password = env_value(DB_PASSWORD_ENV)
    if not host or not database or not user or password is None:
        return None

    port = env_value(DB_PORT_ENV) or "5432"
    return (
        f"postgresql://{quote(user, safe='')}:"
        f"{quote(password, safe='')}@{host}:{port}/{quote(database, safe='')}"
    )


def resolve_database_url(options: dict[str, Any]) -> str | None:
    value = options.get("database_url")
    if value:
        return str(value)
    host = options.get("db_host")
    database = options.get("db_name") or options.get("database")
    user = options.get("db_user")
    password = options.get("db_password")
    if host and database and user and password is not None:
        port = options.get("db_port", 5432)
        return (
            f"postgresql://{quote(str(user), safe='')}:"
            f"{quote(str(password), safe='')}@{host}:{port}/{quote(str(database), safe='')}"
        )
    return database_url_from_env()


def redact_database_url(database_url: str | None) -> str | None:
    if not database_url:
        return None
    try:
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(database_url)
        if "@" not in parts.netloc:
            return database_url
        userinfo, hostinfo = parts.netloc.rsplit("@", 1)
        username = userinfo.split(":", 1)[0]
        return urlunsplit((parts.scheme, f"{username}:***@{hostinfo}", parts.path, parts.query, parts.fragment))
    except ValueError:
        return "***"


def vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{float(value):.8f}" for value in values) + "]"


def json_dumps(value: Any) -> str:
    return json.dumps(json.loads(to_jsonable(value)), ensure_ascii=True)


def chunks_embedding_column_exists(connection: psycopg.Connection[Any]) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'chunks'
                  AND column_name = 'embedding'
            )
            """
        )
        return bool(cursor.fetchone()[0])


def upsert_document_and_chunks(
    *,
    database_url: str,
    document: dict[str, Any],
    chunks: list[dict[str, Any]],
    embedding_model: str,
    embedding_dimensions: int,
) -> dict[str, Any]:
    """Persist source document and chunks; write vector values when available."""

    with psycopg.connect(database_url, autocommit=False) as connection:
        has_vector_column = chunks_embedding_column_exists(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO source_documents (
                    document_id,
                    document_type,
                    title,
                    author_or_source,
                    published_at,
                    raw_location,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (document_id) DO UPDATE
                SET
                    document_type = EXCLUDED.document_type,
                    title = EXCLUDED.title,
                    author_or_source = EXCLUDED.author_or_source,
                    published_at = EXCLUDED.published_at,
                    raw_location = EXCLUDED.raw_location,
                    metadata = EXCLUDED.metadata
                RETURNING id::text
                """,
                (
                    document["document_id"],
                    document.get("document_type") or "memo",
                    document.get("title") or "Untitled document",
                    document.get("author_or_source"),
                    document.get("published_at"),
                    document.get("raw_location") or f"skill://{document['document_id']}",
                    json_dumps(document.get("metadata") or {}),
                ),
            )
            document_row_id = cursor.fetchone()[0]

            persisted_chunk_ids: list[str] = []
            persisted_chunk_row_ids: list[str] = []
            for index, chunk in enumerate(chunks, start=1):
                chunk_index = int(chunk.get("index") or chunk.get("chunk_index") or index)
                params = {
                    "chunk_id": chunk["chunk_id"],
                    "document_id": chunk["document_id"],
                    "chunk_index": chunk_index,
                    "text": chunk["text"],
                    "page_or_offset": chunk.get("page_or_offset"),
                    "embedding_id": chunk.get("embedding_id"),
                    "embedding_model": embedding_model,
                    "embedding_dimensions": embedding_dimensions,
                    "citation_label": chunk.get("citation_label"),
                    "token_count": chunk.get("token_count"),
                    "metadata": json_dumps(chunk.get("metadata") or {}),
                }

                if has_vector_column and chunk.get("embedding") is not None:
                    cursor.execute(
                        """
                        INSERT INTO chunks (
                            chunk_id,
                            document_id,
                            chunk_index,
                            text,
                            page_or_offset,
                            embedding_id,
                            embedding_model,
                            embedding_dimensions,
                            citation_label,
                            token_count,
                            metadata,
                            embedding
                        )
                        VALUES (
                            %(chunk_id)s,
                            %(document_id)s,
                            %(chunk_index)s,
                            %(text)s,
                            %(page_or_offset)s,
                            %(embedding_id)s,
                            %(embedding_model)s,
                            %(embedding_dimensions)s,
                            %(citation_label)s,
                            %(token_count)s,
                            %(metadata)s::jsonb,
                            %(embedding)s::vector
                        )
                        ON CONFLICT (chunk_id) DO UPDATE
                        SET
                            document_id = EXCLUDED.document_id,
                            chunk_index = EXCLUDED.chunk_index,
                            text = EXCLUDED.text,
                            page_or_offset = EXCLUDED.page_or_offset,
                            embedding_id = EXCLUDED.embedding_id,
                            embedding_model = EXCLUDED.embedding_model,
                            embedding_dimensions = EXCLUDED.embedding_dimensions,
                            citation_label = EXCLUDED.citation_label,
                            token_count = EXCLUDED.token_count,
                            metadata = EXCLUDED.metadata,
                            embedding = EXCLUDED.embedding
                        RETURNING id::text
                        """,
                        {**params, "embedding": vector_literal(chunk["embedding"])},
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO chunks (
                            chunk_id,
                            document_id,
                            chunk_index,
                            text,
                            page_or_offset,
                            embedding_id,
                            embedding_model,
                            embedding_dimensions,
                            citation_label,
                            token_count,
                            metadata
                        )
                        VALUES (
                            %(chunk_id)s,
                            %(document_id)s,
                            %(chunk_index)s,
                            %(text)s,
                            %(page_or_offset)s,
                            %(embedding_id)s,
                            %(embedding_model)s,
                            %(embedding_dimensions)s,
                            %(citation_label)s,
                            %(token_count)s,
                            %(metadata)s::jsonb
                        )
                        ON CONFLICT (chunk_id) DO UPDATE
                        SET
                            document_id = EXCLUDED.document_id,
                            chunk_index = EXCLUDED.chunk_index,
                            text = EXCLUDED.text,
                            page_or_offset = EXCLUDED.page_or_offset,
                            embedding_id = EXCLUDED.embedding_id,
                            embedding_model = EXCLUDED.embedding_model,
                            embedding_dimensions = EXCLUDED.embedding_dimensions,
                            citation_label = EXCLUDED.citation_label,
                            token_count = EXCLUDED.token_count,
                            metadata = EXCLUDED.metadata
                        RETURNING id::text
                        """,
                        params,
                    )

                persisted_chunk_ids.append(chunk["chunk_id"])
                persisted_chunk_row_ids.append(cursor.fetchone()[0])

        connection.commit()

    return {
        "document_id": document["document_id"],
        "document_row_id": document_row_id,
        "chunk_ids": persisted_chunk_ids,
        "chunk_row_ids": persisted_chunk_row_ids,
        "chunk_count": len(persisted_chunk_ids),
        "vector_column_used": has_vector_column,
    }


def upsert_wiki_revision(
    *,
    database_url: str,
    revision: dict[str, Any],
    page: dict[str, Any],
) -> dict[str, Any]:
    """Persist a wiki page shell and draft revision without accepting it."""

    with psycopg.connect(database_url, autocommit=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO wiki_pages (
                    page_id,
                    namespace,
                    page_type,
                    title,
                    body,
                    source_refs,
                    confidence,
                    open_questions
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)
                ON CONFLICT (page_id) DO UPDATE
                SET
                    namespace = EXCLUDED.namespace,
                    page_type = EXCLUDED.page_type,
                    title = EXCLUDED.title,
                    source_refs = EXCLUDED.source_refs,
                    confidence = EXCLUDED.confidence,
                    open_questions = EXCLUDED.open_questions
                RETURNING id::text
                """,
                (
                    page["page_id"],
                    page.get("namespace") or "/wiki/drafts",
                    page.get("page_type") or "principle",
                    page.get("title") or revision.get("change_summary") or page["page_id"],
                    page.get("body") or "",
                    json_dumps(page.get("source_refs") or revision.get("source_refs") or []),
                    page.get("confidence") or "low",
                    json_dumps(page.get("open_questions") or []),
                ),
            )
            page_row_id = cursor.fetchone()[0]

            cursor.execute(
                """
                INSERT INTO wiki_revisions (
                    revision_id,
                    page_id,
                    operation,
                    change_summary,
                    before_refs,
                    after_refs,
                    diff_summary,
                    proposed_body,
                    source_refs,
                    verification_result_id,
                    status,
                    review_actions,
                    requested_changes,
                    created_by_agent,
                    created_at
                )
                VALUES (
                    %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s::jsonb,
                    %s, %s, %s::jsonb, %s::jsonb, %s, %s
                )
                ON CONFLICT (revision_id) DO UPDATE
                SET
                    page_id = EXCLUDED.page_id,
                    operation = EXCLUDED.operation,
                    change_summary = EXCLUDED.change_summary,
                    before_refs = EXCLUDED.before_refs,
                    after_refs = EXCLUDED.after_refs,
                    diff_summary = EXCLUDED.diff_summary,
                    proposed_body = EXCLUDED.proposed_body,
                    source_refs = EXCLUDED.source_refs,
                    verification_result_id = EXCLUDED.verification_result_id,
                    status = EXCLUDED.status,
                    review_actions = EXCLUDED.review_actions,
                    requested_changes = EXCLUDED.requested_changes,
                    created_by_agent = EXCLUDED.created_by_agent
                RETURNING id::text
                """,
                (
                    revision["revision_id"],
                    revision["page_id"],
                    revision.get("operation") or "update",
                    revision.get("change_summary") or "Proposed wiki revision.",
                    json_dumps(revision.get("before_refs") or []),
                    json_dumps(revision.get("after_refs") or []),
                    revision.get("diff_summary") or "Review proposed_body before accepting.",
                    revision["proposed_body"],
                    json_dumps(revision.get("source_refs") or []),
                    revision.get("verification_result_id"),
                    revision.get("status") or "draft",
                    json_dumps(revision.get("review_actions") or []),
                    json_dumps(revision.get("requested_changes") or []),
                    revision.get("created_by_agent") or "skill:create_wiki_revision",
                    revision.get("created_at"),
                ),
            )
            revision_row_id = cursor.fetchone()[0]

        connection.commit()

    return {
        "page_id": page["page_id"],
        "page_row_id": page_row_id,
        "revision_id": revision["revision_id"],
        "revision_row_id": revision_row_id,
    }


def upsert_report_draft(
    *,
    database_url: str,
    report: dict[str, Any],
) -> dict[str, Any]:
    """Persist a report draft without promoting it to final output."""

    with psycopg.connect(database_url, autocommit=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO report_drafts (
                    report_id,
                    report_type,
                    title,
                    as_of,
                    sections,
                    claims,
                    numbers,
                    source_refs,
                    actions,
                    verification_status
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s)
                ON CONFLICT (report_id) DO UPDATE
                SET
                    report_type = EXCLUDED.report_type,
                    title = EXCLUDED.title,
                    as_of = EXCLUDED.as_of,
                    sections = EXCLUDED.sections,
                    claims = EXCLUDED.claims,
                    numbers = EXCLUDED.numbers,
                    source_refs = EXCLUDED.source_refs,
                    actions = EXCLUDED.actions,
                    verification_status = EXCLUDED.verification_status
                RETURNING id::text
                """,
                (
                    report["report_id"],
                    report["report_type"],
                    report["title"],
                    report.get("as_of"),
                    json_dumps(report.get("sections") or []),
                    json_dumps(report.get("claims") or []),
                    json_dumps(report.get("numbers") or []),
                    json_dumps(report.get("source_refs") or []),
                    json_dumps(report.get("actions") or []),
                    str(report.get("verification_status") or "pending"),
                ),
            )
            report_row_id = cursor.fetchone()[0]
        connection.commit()

    return {"report_id": report["report_id"], "report_row_id": report_row_id}


def search_chunks(
    *,
    database_url: str,
    query: str,
    top_k: int,
    embedding: Sequence[float] | None = None,
) -> list[dict[str, Any]]:
    with psycopg.connect(database_url) as connection:
        has_vector_column = chunks_embedding_column_exists(connection)
        with connection.cursor(row_factory=dict_row) as cursor:
            if has_vector_column and embedding is not None:
                cursor.execute(
                    sql.SQL(
                        """
                        SELECT
                            chunk_id,
                            document_id,
                            text,
                            page_or_offset,
                            embedding_id,
                            citation_label,
                            1 - (embedding <=> %s::vector) AS score
                        FROM chunks
                        WHERE embedding IS NOT NULL
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                        """
                    ),
                    (vector_literal(embedding), vector_literal(embedding), top_k),
                )
            else:
                cursor.execute(
                    """
                    SELECT
                        chunk_id,
                        document_id,
                        text,
                        page_or_offset,
                        embedding_id,
                        citation_label,
                        ts_rank_cd(to_tsvector('simple', text), plainto_tsquery('simple', %s)) AS score
                    FROM chunks
                    WHERE to_tsvector('simple', text) @@ plainto_tsquery('simple', %s)
                    ORDER BY score DESC
                    LIMIT %s
                    """,
                    (query, query, top_k),
                )
            return [dict(row) for row in cursor.fetchall()]
