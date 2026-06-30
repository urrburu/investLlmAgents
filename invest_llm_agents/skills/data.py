"""Data access catalog skills with fixture-first LangGraph implementations."""

from __future__ import annotations

from typing import Any

from invest_llm_agents.common.enums import ErrorCode, SkillEffect
from invest_llm_agents.common.skill import SkillInput, SkillOutput
from invest_llm_agents.skills.base import coerce_mapping_list, normalize_text, run_skill_graph, source_refs_from_payload


def fetch_news(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("fetch_news", payload, _fetch_news)


def fetch_filings(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("fetch_filings", payload, _fetch_filings)


def fetch_financials(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("fetch_financials", payload, _fetch_financials)


def load_journal_entries(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("load_journal_entries", payload, _load_journal_entries)


def load_current_holdings(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("load_current_holdings", payload, _load_current_holdings)


def _filter_items(items: list[dict[str, Any]], payload: SkillInput) -> list[dict[str, Any]]:
    ticker = normalize_text(payload.options.get("ticker")).upper()
    keywords = [normalize_text(value).casefold() for value in payload.options.get("keywords", []) if normalize_text(value)]
    filtered = []
    for item in items:
        item_ticker = normalize_text(item.get("ticker") or item.get("symbol")).upper()
        haystack = " ".join(str(value) for value in item.values()).casefold()
        ticker_ok = not ticker or item_ticker == ticker or ticker in haystack
        keyword_ok = not keywords or any(keyword in haystack for keyword in keywords)
        if ticker_ok and keyword_ok:
            filtered.append(item)
    return filtered


def _fixture_or_review(payload: SkillInput, key: str, skill: str) -> SkillOutput | list[dict[str, Any]]:
    items = coerce_mapping_list(payload.options.get(key) or payload.options.get("items"))
    if items:
        return items
    return SkillOutput.needs_human_review(
        ErrorCode.MISSING_REQUIRED_INPUT,
        f"{skill} requires provided data until an external adapter is configured.",
        details={
            "required_inputs": [key],
            "blocked_reasons": [f"No {key} source was configured or supplied."],
            "data_status": "missing",
        },
        effect=SkillEffect.READ_EXTERNAL,
    )


def _fetch_news(payload: SkillInput) -> SkillOutput:
    items_or_output = _fixture_or_review(payload, "news", "fetch_news")
    if isinstance(items_or_output, SkillOutput):
        return items_or_output
    items = _filter_items(items_or_output, payload)
    warnings = [f"news item {index + 1} has no as_of timestamp." for index, item in enumerate(items) if not item.get("as_of")]
    return SkillOutput.ok(
        {"news": items, "news_count": len(items), "data_status": "complete" if not warnings else "partial"},
        effect=SkillEffect.READ_EXTERNAL,
        source_refs=source_refs_from_payload(payload),
        warnings=warnings,
    )


def _fetch_filings(payload: SkillInput) -> SkillOutput:
    items_or_output = _fixture_or_review(payload, "filings", "fetch_filings")
    if isinstance(items_or_output, SkillOutput):
        return items_or_output
    items = _filter_items(items_or_output, payload)
    warnings = [f"filing item {index + 1} has no as_of timestamp." for index, item in enumerate(items) if not item.get("as_of")]
    return SkillOutput.ok(
        {"filings": items, "filing_count": len(items), "data_status": "complete" if not warnings else "partial"},
        effect=SkillEffect.READ_EXTERNAL,
        source_refs=source_refs_from_payload(payload),
        warnings=warnings,
    )


def _fetch_financials(payload: SkillInput) -> SkillOutput:
    financials = payload.options.get("financials")
    if not financials:
        return SkillOutput.needs_human_review(
            ErrorCode.MISSING_REQUIRED_INPUT,
            "fetch_financials requires provided financials until an external adapter is configured.",
            details={
                "required_inputs": ["financials"],
                "blocked_reasons": ["No financial data source was configured or supplied."],
                "data_status": "missing",
            },
            effect=SkillEffect.READ_EXTERNAL,
        )
    warnings = []
    if isinstance(financials, dict) and not financials.get("as_of"):
        warnings.append("financials payload has no as_of timestamp.")
    return SkillOutput.ok(
        {
            "financials": financials,
            "ticker": normalize_text(payload.options.get("ticker")).upper() or None,
            "data_status": "complete" if not warnings else "partial",
        },
        effect=SkillEffect.READ_EXTERNAL,
        source_refs=source_refs_from_payload(payload),
        warnings=warnings,
    )


def _load_journal_entries(payload: SkillInput) -> SkillOutput:
    entries = coerce_mapping_list(payload.options.get("journal_entries") or payload.options.get("entries"))
    if not entries:
        return SkillOutput.needs_human_review(
            ErrorCode.MISSING_REQUIRED_INPUT,
            "No journal entries were supplied.",
            details={
                "required_inputs": ["journal_entries"],
                "blocked_reasons": ["No journal entries were supplied."],
            },
        )
    return SkillOutput.ok({"journal_entries": entries, "entry_count": len(entries)}, source_refs=source_refs_from_payload(payload))


def _load_current_holdings(payload: SkillInput) -> SkillOutput:
    snapshot = payload.options.get("portfolio_snapshot")
    holdings = coerce_mapping_list(payload.options.get("holdings"))
    if isinstance(snapshot, dict) and not holdings:
        holdings = coerce_mapping_list(snapshot.get("holdings"))
    if not holdings:
        return SkillOutput.needs_human_review(
            ErrorCode.MISSING_REQUIRED_INPUT,
            "No current holdings were supplied.",
            details={
                "required_inputs": ["holdings", "portfolio_snapshot.holdings"],
                "blocked_reasons": ["No current holdings were supplied."],
                "data_status": "missing",
            },
        )
    normalized = []
    warnings = []
    for holding in holdings:
        data_status = holding.get("data_status")
        if not data_status:
            if holding.get("market_price") in (None, "") and holding.get("market_value") in (None, ""):
                data_status = "missing_price"
            elif holding.get("cost_basis") in (None, ""):
                data_status = "missing_cost"
            else:
                data_status = "complete"
        normalized_holding = {**holding, "data_status": data_status}
        if data_status != "complete":
            warnings.append(f"{normalized_holding.get('ticker', 'holding')} has data_status={data_status}.")
        normalized.append(normalized_holding)
    return SkillOutput.ok(
        {
            "portfolio_snapshot": snapshot,
            "holdings": normalized,
            "holding_count": len(normalized),
            "data_status": "complete" if not warnings else "partial",
            "blocked_reasons": warnings,
        },
        source_refs=source_refs_from_payload(payload),
        warnings=warnings,
    )
