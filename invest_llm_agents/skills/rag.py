"""RAG catalog skills implemented as LangGraph-backed callables."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from invest_llm_agents.common.enums import ErrorCode, SkillEffect
from invest_llm_agents.common.skill import SkillInput, SkillOutput
from invest_llm_agents.skills.base import (
    chunk_text,
    coerce_mapping_list,
    deterministic_embedding,
    extract_body_text,
    lexical_score,
    missing_required_output,
    normalize_text,
    run_skill_graph,
    source_refs_from_payload,
    stable_id,
)
from invest_llm_agents.skills.storage import (
    redact_database_url,
    resolve_database_url,
    search_chunks,
    upsert_document_and_chunks,
)


def parse_document(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("parse_document", payload, _parse_document)


def chunk_document(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("chunk_document", payload, _chunk_document)


def embed_chunks(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("embed_chunks", payload, _embed_chunks)


def retrieve_related_chunks(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("retrieve_related_chunks", payload, _retrieve_related_chunks)


def rerank_context(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("rerank_context", payload, _rerank_context)


def _read_text_file(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp949", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_pdf(path: Path) -> tuple[str, dict[str, Any]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    page_texts = []
    for index, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        if page_text.strip():
            page_texts.append({"page": index, "text": page_text.strip()})

    metadata = {str(key).lstrip("/"): str(value) for key, value in (reader.metadata or {}).items()}
    return "\n\n".join(item["text"] for item in page_texts), {
        "page_count": len(reader.pages),
        "parsed_pages": [item["page"] for item in page_texts],
        "pdf_metadata": metadata,
    }


def _document_text_and_metadata(payload: SkillInput) -> tuple[str, dict[str, Any]]:
    inline_text = extract_body_text(payload.options)
    if inline_text:
        return inline_text, {"parser": "inline_text", "raw_location": payload.options.get("raw_location")}

    raw_location = (
        payload.options.get("file_path")
        or payload.options.get("path")
        or payload.options.get("raw_location")
    )
    if not raw_location:
        return "", {"parser": None}

    path = Path(str(raw_location)).expanduser()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Document file does not exist: {path}")

    suffix = path.suffix.casefold()
    if suffix == ".pdf":
        text, metadata = _parse_pdf(path)
        return text, {"parser": "pypdf", "raw_location": str(path), **metadata}

    return _read_text_file(path), {"parser": "text_file", "raw_location": str(path)}


def _parse_document(payload: SkillInput) -> SkillOutput:
    try:
        text, parse_metadata = _document_text_and_metadata(payload)
    except (FileNotFoundError, OSError, ValueError) as exc:
        return SkillOutput.blocked(
            ErrorCode.SOURCE_PARSE_FAILED,
            str(exc),
            details={"required_inputs": ["text", "file_path", "raw_location"]},
            effect=SkillEffect.READ_EXTERNAL,
        )

    if not text:
        return SkillOutput.blocked(
            ErrorCode.SOURCE_PARSE_FAILED,
            "No parseable document text was supplied.",
            details={"required_inputs": ["text", "raw_text", "document.body"]},
            effect=SkillEffect.READ_EXTERNAL if parse_metadata.get("raw_location") else SkillEffect.PURE,
        )

    document_id = payload.options.get("document_id") or stable_id("document", text)
    title = payload.options.get("title") or "Untitled document"
    document_type = payload.options.get("document_type") or "memo"
    parsed = {
        "document_id": document_id,
        "document_type": document_type,
        "title": title,
        "text": text,
        "char_count": len(text),
        "line_count": text.count("\n") + 1,
        "parser": parse_metadata.get("parser") or "inline_text",
        "raw_location": parse_metadata.get("raw_location"),
        "metadata": {**dict(payload.options.get("metadata") or {}), **parse_metadata},
    }
    effect = SkillEffect.READ_EXTERNAL if parse_metadata.get("raw_location") else SkillEffect.PURE
    return SkillOutput.ok(parsed, effect=effect, source_refs=source_refs_from_payload(payload))


def _chunk_document(payload: SkillInput) -> SkillOutput:
    text = extract_body_text(payload.options)
    if not text:
        return missing_required_output(["text"], skill="chunk_document")

    chunk_size = int(payload.options.get("chunk_size", 1200))
    overlap = int(payload.options.get("overlap", 150))
    document_id = payload.options.get("document_id") or stable_id("document", text)
    citation_prefix = payload.options.get("citation_label") or document_id

    chunks = []
    for chunk in chunk_text(text, chunk_size=chunk_size, overlap=overlap):
        chunk_id = stable_id("chunk", {"document_id": document_id, "index": chunk["index"], "text": chunk["text"]})
        chunks.append(
            {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "text": chunk["text"],
                "page_or_offset": chunk["page_or_offset"],
                "citation_label": f"{citation_prefix} #{chunk['index']}",
            }
        )

    return SkillOutput.ok(
        {
            "document_id": document_id,
            "chunk_count": len(chunks),
            "chunks": chunks,
            "chunk_size": chunk_size,
            "overlap": overlap,
        },
        source_refs=source_refs_from_payload(payload),
    )


def _embed_chunks(payload: SkillInput) -> SkillOutput:
    chunks = coerce_mapping_list(payload.options.get("chunks"))
    if not chunks:
        return missing_required_output(["chunks"], skill="embed_chunks")

    dimensions = int(payload.options.get("dimensions", 1536))
    embedding_model = str(payload.options.get("embedding_model") or "deterministic-sha256")
    embedded: list[dict[str, Any]] = []
    for chunk in chunks:
        text = normalize_text(chunk.get("text"))
        if not text:
            continue
        chunk_id = chunk.get("chunk_id") or stable_id("chunk", text)
        embedding_id = chunk.get("embedding_id") or stable_id("embedding", {"chunk_id": chunk_id, "dimensions": dimensions})
        embedded.append(
            {
                **chunk,
                "chunk_id": chunk_id,
                "embedding_id": embedding_id,
                "document_id": chunk.get("document_id") or payload.options.get("document_id") or stable_id("document", text),
                "embedding": deterministic_embedding(text, dimensions=dimensions),
            }
        )

    warnings = []
    storage_status = "generated"
    persisted = None
    database_url = resolve_database_url(payload.options)
    persist = bool(payload.options.get("persist") or payload.options.get("pgvector_table"))
    if persist and database_url:
        document = {
            "document_id": payload.options.get("document_id") or embedded[0]["document_id"],
            "document_type": payload.options.get("document_type") or "memo",
            "title": payload.options.get("title") or "Untitled document",
            "author_or_source": payload.options.get("author_or_source"),
            "published_at": payload.options.get("published_at"),
            "raw_location": payload.options.get("raw_location") or f"skill://{payload.run_id}",
            "metadata": payload.options.get("metadata") or {},
        }
        try:
            persisted = upsert_document_and_chunks(
                database_url=database_url,
                document=document,
                chunks=embedded,
                embedding_model=embedding_model,
                embedding_dimensions=dimensions,
            )
        except Exception as exc:
            return SkillOutput.blocked(
                ErrorCode.PARTIAL_EXTERNAL_OUTAGE,
                "Embedding persistence failed.",
                details={"exception_type": type(exc).__name__, "message": str(exc)},
                data={
                    "chunks": embedded,
                    "embedding_count": len(embedded),
                    "dimensions": dimensions,
                    "embedding_model": embedding_model,
                    "storage_status": "persistence_failed",
                    "database_url": redact_database_url(database_url),
                    "write_log": {
                        "effect": SkillEffect.WRITE_INTERNAL.value,
                        "input_summary": {
                            "chunk_count": len(embedded),
                            "document_id": document["document_id"],
                            "embedding_dimensions": dimensions,
                            "embedding_model": embedding_model,
                        },
                        "target_tables": ["source_documents", "chunks"],
                        "row_ids": {},
                        "rollback": "No rollback is required if the transaction failed before commit.",
                    },
                },
                effect=SkillEffect.WRITE_INTERNAL,
                warnings=warnings,
            )
        storage_status = "persisted"
    elif persist:
        warnings.append("Persistence was requested, but INVEST_LLM_DATABASE_URL/database_url was not supplied.")
        storage_status = "not_persisted"
    else:
        warnings.append("Embeddings were generated in memory; set persist=True and INVEST_LLM_DATABASE_URL to store them.")
        storage_status = "not_persisted"

    output = {
        "chunks": embedded,
        "embedding_count": len(embedded),
        "dimensions": dimensions,
        "embedding_model": embedding_model,
        "storage_status": storage_status,
        "database_url": redact_database_url(database_url),
        "persistence": persisted,
        "write_log": {
            "effect": SkillEffect.WRITE_INTERNAL.value,
            "input_summary": {
                "chunk_count": len(embedded),
                "document_id": embedded[0]["document_id"] if embedded else payload.options.get("document_id"),
                "embedding_dimensions": dimensions,
                "embedding_model": embedding_model,
            },
            "target_tables": ["source_documents", "chunks"],
            "row_ids": persisted or {},
            "rollback": "Delete rows from chunks by chunk_id, then delete source_documents by document_id if no longer referenced.",
        },
    }
    if storage_status == "not_persisted":
        return SkillOutput.partial(output, effect=SkillEffect.WRITE_INTERNAL, warnings=warnings)
    return SkillOutput.ok(output, effect=SkillEffect.WRITE_INTERNAL, warnings=warnings)


def _retrieve_related_chunks(payload: SkillInput) -> SkillOutput:
    query = normalize_text(payload.options.get("query"))
    chunks = coerce_mapping_list(payload.options.get("chunks"))
    database_url = resolve_database_url(payload.options)
    if query and database_url and not chunks:
        top_k = int(payload.options.get("top_k", 5))
        dimensions = int(payload.options.get("dimensions", 1536))
        try:
            results = search_chunks(
                database_url=database_url,
                query=query,
                top_k=top_k,
                embedding=deterministic_embedding(query, dimensions=dimensions),
            )
        except Exception as exc:
            return SkillOutput.needs_human_review(
                ErrorCode.PARTIAL_EXTERNAL_OUTAGE,
                "Chunk retrieval from PostgreSQL failed.",
                details={"exception_type": type(exc).__name__, "message": str(exc)},
                data={"query": query, "results": [], "result_count": 0, "source": "postgresql"},
                effect=SkillEffect.READ_EXTERNAL,
            )
        return SkillOutput.ok(
            {"query": query, "results": results, "result_count": len(results), "source": "postgresql"},
            effect=SkillEffect.READ_EXTERNAL,
            source_refs=source_refs_from_payload(payload),
        )

    if not query or not chunks:
        return missing_required_output(["query", "chunks"], skill="retrieve_related_chunks")

    top_k = int(payload.options.get("top_k", 5))
    scored = []
    for chunk in chunks:
        text = normalize_text(chunk.get("text"))
        score = lexical_score(query, text)
        if score > 0 or payload.options.get("include_zero_score"):
            scored.append({**chunk, "score": round(score, 6), "score_method": "lexical_overlap"})

    scored.sort(key=lambda item: item["score"], reverse=True)
    return SkillOutput.ok(
        {"query": query, "results": scored[:top_k], "result_count": min(len(scored), top_k)},
        effect=SkillEffect.READ_EXTERNAL,
        source_refs=source_refs_from_payload(payload),
    )


def _rerank_context(payload: SkillInput) -> SkillOutput:
    query = normalize_text(payload.options.get("query"))
    candidates = coerce_mapping_list(payload.options.get("results") or payload.options.get("chunks"))
    if not query or not candidates:
        return missing_required_output(["query", "results"], skill="rerank_context")

    reranked = []
    for index, candidate in enumerate(candidates):
        base_score = float(candidate.get("score") or 0)
        text_score = lexical_score(query, normalize_text(candidate.get("text")))
        final_score = round((base_score * 0.6) + (text_score * 0.4), 6)
        reranked.append({**candidate, "original_rank": index + 1, "rerank_score": final_score})

    reranked.sort(key=lambda item: item["rerank_score"], reverse=True)
    return SkillOutput.ok({"query": query, "results": reranked, "result_count": len(reranked)})
