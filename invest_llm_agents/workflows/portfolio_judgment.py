"""Portfolio judgment workflow graph built from catalog skills."""

from __future__ import annotations

from typing import Any

from invest_llm_agents.common.skill import SkillInput, SkillOutput
from invest_llm_agents.workflows.base import (
    WorkflowState,
    aggregate_workflow_output,
    build_linear_workflow_graph,
    coerce_rows,
    collect_staleness_items,
    invoke_step,
    report_to_text,
    run_workflow_graph,
    skipped_step,
    step_data,
)


def _load_current_holdings(state: WorkflowState) -> WorkflowState:
    return invoke_step(state, "load_current_holdings")


def _fetch_price_data(state: WorkflowState) -> WorkflowState:
    options = dict(state.get("options") or {})
    if not (options.get("prices") or options.get("price_data")):
        return skipped_step("fetch_price_data", "Holdings will be used as supplied because no separate prices were provided.")
    return invoke_step(state, "fetch_price_data")


def _holdings_with_prices(state: WorkflowState) -> list[dict[str, Any]]:
    holdings = coerce_rows(step_data(state, "load_current_holdings").get("holdings"))
    prices = coerce_rows(step_data(state, "fetch_price_data").get("prices"))
    price_by_ticker = {str(price.get("ticker", "")).upper(): price for price in prices}

    enriched = []
    for holding in holdings:
        ticker = str(holding.get("ticker", "")).upper()
        price = price_by_ticker.get(ticker)
        if price and holding.get("market_price") in (None, ""):
            holding = {**holding, "market_price": price.get("price"), "price_as_of": price.get("as_of")}
        enriched.append(holding)
    return enriched


def _calculate_weights(state: WorkflowState) -> WorkflowState:
    return invoke_step(state, "calculate_weights", options={"holdings": _holdings_with_prices(state)})


def _calculate_returns(state: WorkflowState) -> WorkflowState:
    return invoke_step(state, "calculate_returns", options={"holdings": _holdings_with_prices(state)})


def _detect_concentration(state: WorkflowState) -> WorkflowState:
    holdings = step_data(state, "calculate_weights").get("holdings") or _holdings_with_prices(state)
    return invoke_step(state, "detect_concentration", options={"holdings": holdings})


def _retrieve_related_chunks(state: WorkflowState) -> WorkflowState:
    options = dict(state.get("options") or {})
    if not any(options.get(key) for key in ("query", "chunks", "use_rag", "database_url")):
        return skipped_step("retrieve_related_chunks", "No RAG query, chunks, or database URL was supplied.")
    query = options.get("query") or "portfolio concentration risk sizing process"
    return invoke_step(state, "retrieve_related_chunks", options={"query": query})


def _rerank_context(state: WorkflowState) -> WorkflowState:
    retrieved = step_data(state, "retrieve_related_chunks")
    results = retrieved.get("results") or []
    query = retrieved.get("query") or state.get("options", {}).get("query")
    if not query or not results:
        return skipped_step("rerank_context", "No retrieved context was available to rerank.")
    return invoke_step(state, "rerank_context", options={"query": query, "results": results})


def _generate_portfolio_report(state: WorkflowState) -> WorkflowState:
    weighted = step_data(state, "calculate_weights")
    return invoke_step(
        state,
        "generate_portfolio_report",
        options={
            "holdings": weighted.get("holdings") or _holdings_with_prices(state),
            "metrics": weighted,
            "returns": step_data(state, "calculate_returns").get("returns"),
            "concentration": step_data(state, "detect_concentration"),
            "context": step_data(state, "rerank_context").get("results")
            or step_data(state, "retrieve_related_chunks").get("results"),
        },
    )


def _check_stale_data(state: WorkflowState) -> WorkflowState:
    items = collect_staleness_items(
        step_data(state, "fetch_price_data").get("prices"),
        _holdings_with_prices(state),
    )
    if not items:
        return skipped_step("check_stale_data", "No timestamped portfolio data was available.")
    return invoke_step(state, "check_stale_data", options={"items": items})


def _check_recommendation_language(state: WorkflowState) -> WorkflowState:
    report = step_data(state, "generate_portfolio_report").get("report") or {}
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
    output = aggregate_workflow_output(
        workflow_name="portfolio_judgment",
        state=state,
        data={
            "report": step_data(state, "generate_portfolio_report").get("report"),
            "weights": step_data(state, "calculate_weights"),
            "returns": step_data(state, "calculate_returns"),
            "concentration": step_data(state, "detect_concentration"),
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


def build_portfolio_judgment_graph():
    return build_linear_workflow_graph(
        [
            ("load_current_holdings", _load_current_holdings),
            ("fetch_price_data", _fetch_price_data),
            ("calculate_weights", _calculate_weights),
            ("calculate_returns", _calculate_returns),
            ("detect_concentration", _detect_concentration),
            ("retrieve_related_chunks", _retrieve_related_chunks),
            ("rerank_context", _rerank_context),
            ("generate_portfolio_report", _generate_portfolio_report),
            ("check_stale_data", _check_stale_data),
            ("check_recommendation_language", _check_recommendation_language),
            ("quality_score", _quality_score),
            ("finalize", _finalize),
        ]
    )


def run_portfolio_judgment(payload: SkillInput) -> SkillOutput:
    return run_workflow_graph(build_portfolio_judgment_graph(), payload)
