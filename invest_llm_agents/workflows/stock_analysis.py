"""Stock analysis workflow graph built from catalog skills."""

from __future__ import annotations

from typing import Any

from invest_llm_agents.common.skill import SkillInput, SkillOutput
from invest_llm_agents.workflows.base import (
    WorkflowState,
    aggregate_workflow_output,
    build_linear_workflow_graph,
    collect_staleness_items,
    first_present,
    invoke_step,
    report_to_text,
    run_workflow_graph,
    skipped_step,
    step_data,
)


def _ticker_from_state(state: WorkflowState) -> str | None:
    normalized = step_data(state, "normalize_ticker").get("tickers") or []
    return first_present(normalized[0] if normalized else None, state.get("options", {}).get("ticker"))


def _normalize_ticker(state: WorkflowState) -> WorkflowState:
    return invoke_step(state, "normalize_ticker")


def _fetch_price_data(state: WorkflowState) -> WorkflowState:
    return invoke_step(state, "fetch_price_data", options={"ticker": _ticker_from_state(state)})


def _fetch_financials(state: WorkflowState) -> WorkflowState:
    return invoke_step(state, "fetch_financials", options={"ticker": _ticker_from_state(state)})


def _fetch_news(state: WorkflowState) -> WorkflowState:
    return invoke_step(state, "fetch_news", options={"ticker": _ticker_from_state(state)})


def _fetch_filings(state: WorkflowState) -> WorkflowState:
    return invoke_step(state, "fetch_filings", options={"ticker": _ticker_from_state(state)})


def _retrieve_related_chunks(state: WorkflowState) -> WorkflowState:
    options = dict(state.get("options") or {})
    if not any(options.get(key) for key in ("query", "chunks", "use_rag", "database_url")):
        return skipped_step("retrieve_related_chunks", "No RAG query, chunks, or database URL was supplied.")

    ticker = _ticker_from_state(state) or "stock"
    query = options.get("query") or f"{ticker} investment thesis risk valuation"
    return invoke_step(state, "retrieve_related_chunks", options={"query": query})


def _rerank_context(state: WorkflowState) -> WorkflowState:
    retrieved = step_data(state, "retrieve_related_chunks")
    results = retrieved.get("results") or []
    query = retrieved.get("query") or state.get("options", {}).get("query")
    if not query or not results:
        return skipped_step("rerank_context", "No retrieved context was available to rerank.")
    return invoke_step(state, "rerank_context", options={"query": query, "results": results})


def _generate_stock_snapshot(state: WorkflowState) -> WorkflowState:
    options: dict[str, Any] = {
        "ticker": _ticker_from_state(state),
        "price_data": step_data(state, "fetch_price_data").get("prices"),
        "financials": step_data(state, "fetch_financials").get("financials"),
        "news": step_data(state, "fetch_news").get("news"),
        "filings": step_data(state, "fetch_filings").get("filings"),
        "context": step_data(state, "rerank_context").get("results")
        or step_data(state, "retrieve_related_chunks").get("results"),
    }
    return invoke_step(state, "generate_stock_snapshot", options=options)


def _check_stale_data(state: WorkflowState) -> WorkflowState:
    items = collect_staleness_items(
        step_data(state, "fetch_price_data").get("prices"),
        [step_data(state, "fetch_financials").get("financials")],
        step_data(state, "fetch_news").get("news"),
        step_data(state, "fetch_filings").get("filings"),
    )
    if not items:
        return skipped_step("check_stale_data", "No timestamped stock data was available.")
    return invoke_step(state, "check_stale_data", options={"items": items})


def _check_recommendation_language(state: WorkflowState) -> WorkflowState:
    report = step_data(state, "generate_stock_snapshot").get("report") or {}
    text = report_to_text(report)
    if not text:
        return skipped_step("check_recommendation_language", "No generated report text was available.")
    return invoke_step(state, "check_recommendation_language", options={"text": text})


def _quality_score(state: WorkflowState) -> WorkflowState:
    stale = step_data(state, "check_stale_data")
    language = step_data(state, "check_recommendation_language")
    checks = [
        *list(stale.get("staleness_checks") or []),
        *list(language.get("language_checks") or []),
    ]
    if not checks:
        return skipped_step("quality_score", "No verification checks were produced.")
    return invoke_step(state, "quality_score", options={"checks": checks})


def _finalize(state: WorkflowState) -> WorkflowState:
    report = step_data(state, "generate_stock_snapshot").get("report")
    output = aggregate_workflow_output(
        workflow_name="stock_analysis",
        state=state,
        data={
            "ticker": _ticker_from_state(state),
            "report": report,
            "quality": step_data(state, "quality_score"),
            "verification": {
                "staleness": step_data(state, "check_stale_data"),
                "language": step_data(state, "check_recommendation_language"),
            },
            "context": step_data(state, "rerank_context").get("results")
            or step_data(state, "retrieve_related_chunks").get("results")
            or [],
        },
    )
    return {"final_output": output}


def build_stock_analysis_graph():
    return build_linear_workflow_graph(
        [
            ("normalize_ticker", _normalize_ticker),
            ("fetch_price_data", _fetch_price_data),
            ("fetch_financials", _fetch_financials),
            ("fetch_news", _fetch_news),
            ("fetch_filings", _fetch_filings),
            ("retrieve_related_chunks", _retrieve_related_chunks),
            ("rerank_context", _rerank_context),
            ("generate_stock_snapshot", _generate_stock_snapshot),
            ("check_stale_data", _check_stale_data),
            ("check_recommendation_language", _check_recommendation_language),
            ("quality_score", _quality_score),
            ("finalize", _finalize),
        ]
    )


def run_stock_analysis(payload: SkillInput) -> SkillOutput:
    return run_workflow_graph(build_stock_analysis_graph(), payload)
