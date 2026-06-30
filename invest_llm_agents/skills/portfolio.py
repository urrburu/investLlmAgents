"""Portfolio catalog skills implemented as LangGraph-backed callables."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from invest_llm_agents.common.enums import ErrorCode, SkillEffect
from invest_llm_agents.common.skill import SkillInput, SkillOutput
from invest_llm_agents.skills.base import (
    coerce_mapping_list,
    decimal_or_none,
    decimal_to_float,
    missing_required_output,
    normalize_text,
    run_skill_graph,
    source_refs_from_payload,
)


def normalize_ticker(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("normalize_ticker", payload, _normalize_ticker)


def fetch_price_data(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("fetch_price_data", payload, _fetch_price_data)


def calculate_returns(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("calculate_returns", payload, _calculate_returns)


def calculate_weights(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("calculate_weights", payload, _calculate_weights)


def detect_concentration(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("detect_concentration", payload, _detect_concentration)


def _normalize_one_ticker(value: Any) -> str:
    ticker = normalize_text(value).replace(" ", "").replace("/", ".")
    return ticker.upper()


def _normalize_ticker(payload: SkillInput) -> SkillOutput:
    raw_tickers = payload.options.get("tickers")
    if raw_tickers is None:
        raw_ticker = payload.options.get("ticker")
        raw_tickers = [raw_ticker] if raw_ticker else []
    if not raw_tickers:
        return missing_required_output(["ticker"], skill="normalize_ticker")

    aliases = {str(k).casefold(): v for k, v in dict(payload.options.get("ticker_aliases") or {}).items()}
    normalized = []
    ambiguous = []
    for raw in raw_tickers:
        candidate = aliases.get(str(raw).casefold(), raw)
        ticker = _normalize_one_ticker(candidate)
        if not ticker:
            continue
        if isinstance(candidate, list):
            ambiguous.append({"input": raw, "candidates": candidate})
            continue
        normalized.append({"input": raw, "ticker": ticker})

    if ambiguous:
        return SkillOutput.needs_human_review(
            ErrorCode.AMBIGUOUS_TICKER,
            "Ticker input has multiple possible matches.",
            details={"ambiguous": ambiguous},
            data={"normalized": normalized},
        )

    return SkillOutput.ok({"normalized": normalized, "tickers": [item["ticker"] for item in normalized]})


def _fetch_price_data(payload: SkillInput) -> SkillOutput:
    prices = payload.options.get("prices") or payload.options.get("price_data")
    if isinstance(prices, dict):
        rows = [{"ticker": ticker, **(data if isinstance(data, dict) else {"price": data})} for ticker, data in prices.items()]
    else:
        rows = coerce_mapping_list(prices)

    if not rows:
        return SkillOutput.needs_human_review(
            ErrorCode.MISSING_REQUIRED_INPUT,
            "Price data adapter is not configured; supply prices in options.",
            details={
                "required_inputs": ["prices"],
                "blocked_reasons": ["No current price source was available."],
                "data_status": "missing_price",
            },
            effect=SkillEffect.READ_EXTERNAL,
        )

    normalized_rows = []
    warnings = []
    skipped = []
    for row in rows:
        ticker = _normalize_one_ticker(row.get("ticker") or row.get("symbol"))
        price = decimal_to_float(row.get("price") or row.get("close") or row.get("market_price"))
        if not ticker or price is None:
            skipped.append(row)
            continue
        if not row.get("as_of"):
            warnings.append(f"{ticker} price row has no as_of timestamp.")
        normalized_rows.append(
            {
                "ticker": ticker,
                "price": price,
                "as_of": row.get("as_of"),
                "currency": row.get("currency") or payload.options.get("currency") or "USD",
                "source": row.get("source") or "provided",
                "source_url": row.get("source_url"),
                "data_status": "complete" if row.get("as_of") else "partial",
            }
        )

    if not normalized_rows:
        return SkillOutput.needs_human_review(
            ErrorCode.MISSING_REQUIRED_INPUT,
            "No valid price rows were supplied.",
            details={
                "required_inputs": ["prices[].ticker", "prices[].price"],
                "blocked_reasons": ["Every supplied price row was missing ticker or price."],
                "skipped_rows": skipped,
                "data_status": "missing_price",
            },
            effect=SkillEffect.READ_EXTERNAL,
        )

    return SkillOutput.ok(
        {"prices": normalized_rows, "price_count": len(normalized_rows), "skipped_rows": skipped},
        effect=SkillEffect.READ_EXTERNAL,
        source_refs=source_refs_from_payload(payload),
        warnings=warnings,
    )


def _calculate_returns(payload: SkillInput) -> SkillOutput:
    holdings = coerce_mapping_list(payload.options.get("holdings"))
    price_series = coerce_mapping_list(payload.options.get("price_series"))
    returns = []

    for holding in holdings:
        ticker = _normalize_one_ticker(holding.get("ticker"))
        cost = decimal_or_none(holding.get("cost_basis"))
        price = decimal_or_none(holding.get("market_price") or holding.get("price"))
        if ticker and cost is not None and price is not None and cost != 0:
            value = (price - cost) / cost
            returns.append(
                {
                    "ticker": ticker,
                    "return": decimal_to_float(value),
                    "formula": "(market_price - cost_basis) / cost_basis",
                }
            )

    for series in price_series:
        ticker = _normalize_one_ticker(series.get("ticker"))
        start = decimal_or_none(series.get("start_price"))
        end = decimal_or_none(series.get("end_price"))
        if ticker and start is not None and end is not None and start != 0:
            value = (end - start) / start
            returns.append(
                {
                    "ticker": ticker,
                    "return": decimal_to_float(value),
                    "formula": "(end_price - start_price) / start_price",
                }
            )

    if not returns:
        return missing_required_output(["holdings.cost_basis", "holdings.market_price"], skill="calculate_returns")

    return SkillOutput.ok({"returns": returns, "return_count": len(returns)})


def _calculate_weights(payload: SkillInput) -> SkillOutput:
    holdings = coerce_mapping_list(payload.options.get("holdings"))
    if not holdings:
        return missing_required_output(["holdings"], skill="calculate_weights")

    cash = decimal_or_none(payload.options.get("cash")) or Decimal("0")
    enriched = []
    total_value = cash

    for holding in holdings:
        quantity = decimal_or_none(holding.get("quantity")) or Decimal("0")
        price = decimal_or_none(holding.get("market_price") or holding.get("price"))
        market_value = decimal_or_none(holding.get("market_value"))
        if market_value is None and price is not None:
            market_value = quantity * price
        if market_value is None:
            market_value = Decimal("0")
        total_value += market_value
        data_status = holding.get("data_status")
        if not data_status:
            if price is None and decimal_or_none(holding.get("market_value")) is None:
                data_status = "missing_price"
            elif holding.get("cost_basis") in (None, ""):
                data_status = "missing_cost"
            else:
                data_status = "complete"
        enriched.append(
            {
                **holding,
                "ticker": _normalize_one_ticker(holding.get("ticker")),
                "market_value": market_value,
                "data_status": data_status,
            }
        )

    if total_value <= 0:
        return SkillOutput.blocked(
            ErrorCode.INVALID_INPUT,
            "Total portfolio value must be greater than zero.",
            details={"total_value": str(total_value)},
        )

    weighted = []
    for holding in enriched:
        market_value = decimal_or_none(holding.get("market_value")) or Decimal("0")
        weight = market_value / total_value
        weighted.append(
            {
                **{k: v for k, v in holding.items() if k != "market_value"},
                "market_value": decimal_to_float(market_value),
                "weight": decimal_to_float(weight),
                "formula": "market_value / total_portfolio_value",
            }
        )

    warnings = [
        f"{holding['ticker']} has data_status={holding['data_status']}."
        for holding in weighted
        if holding.get("data_status") != "complete"
    ]
    return SkillOutput.ok(
        {
            "holdings": weighted,
            "cash": decimal_to_float(cash),
            "total_value": decimal_to_float(total_value),
            "blocked_reasons": warnings,
        },
        warnings=warnings,
    )


def _detect_concentration(payload: SkillInput) -> SkillOutput:
    holdings = coerce_mapping_list(payload.options.get("holdings"))
    if not holdings:
        return missing_required_output(["holdings"], skill="detect_concentration")

    single_threshold = float(payload.options.get("single_position_threshold", 0.25))
    sector_threshold = float(payload.options.get("sector_threshold", 0.4))
    position_flags = []
    sector_weights: defaultdict[str, float] = defaultdict(float)

    for holding in holdings:
        ticker = _normalize_one_ticker(holding.get("ticker"))
        weight = float(holding.get("weight") or 0)
        sector = normalize_text(holding.get("sector")) or "Unknown"
        sector_weights[sector] += weight
        if weight >= single_threshold:
            position_flags.append(
                {
                    "ticker": ticker,
                    "weight": weight,
                    "threshold": single_threshold,
                    "severity": "high" if weight >= single_threshold * 1.5 else "medium",
                }
            )

    sector_flags = [
        {
            "sector": sector,
            "weight": round(weight, 6),
            "threshold": sector_threshold,
            "severity": "high" if weight >= sector_threshold * 1.25 else "medium",
        }
        for sector, weight in sorted(sector_weights.items(), key=lambda item: item[1], reverse=True)
        if weight >= sector_threshold
    ]

    return SkillOutput.ok(
        {
            "position_flags": position_flags,
            "sector_flags": sector_flags,
            "is_concentrated": bool(position_flags or sector_flags),
        }
    )
