"""Market regime catalog skills implemented with LangGraph."""

from __future__ import annotations

from invest_llm_agents.common.enums import ErrorCode, SkillEffect
from invest_llm_agents.common.skill import SkillInput, SkillOutput
from invest_llm_agents.skills.base import coerce_mapping_list, decimal_to_float, missing_required_output, normalize_text, run_skill_graph


def fetch_market_indices(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("fetch_market_indices", payload, _fetch_market_indices)


def fetch_macro_indicators(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("fetch_macro_indicators", payload, _fetch_macro_indicators)


def analyze_sector_rotation(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("analyze_sector_rotation", payload, _analyze_sector_rotation)


def detect_risk_on_off(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("detect_risk_on_off", payload, _detect_risk_on_off)


def generate_market_brief(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("generate_market_brief", payload, _generate_market_brief)


def _fetch_market_indices(payload: SkillInput) -> SkillOutput:
    indices = coerce_mapping_list(payload.options.get("indices") or payload.options.get("market_indices"))
    if not indices:
        return SkillOutput.needs_human_review(
            ErrorCode.MISSING_REQUIRED_INPUT,
            "Market index data adapter is not configured; supply indices in options.",
            details={
                "required_inputs": ["indices"],
                "blocked_reasons": ["No market index source was configured or supplied."],
                "data_status": "missing",
            },
            effect=SkillEffect.READ_EXTERNAL,
        )
    warnings = [f"index item {index + 1} has no as_of timestamp." for index, item in enumerate(indices) if not item.get("as_of")]
    return SkillOutput.ok(
        {"indices": indices, "index_count": len(indices), "data_status": "complete" if not warnings else "partial"},
        effect=SkillEffect.READ_EXTERNAL,
        warnings=warnings,
    )


def _fetch_macro_indicators(payload: SkillInput) -> SkillOutput:
    indicators = coerce_mapping_list(payload.options.get("macro_indicators") or payload.options.get("indicators"))
    if not indicators:
        return SkillOutput.needs_human_review(
            ErrorCode.MISSING_REQUIRED_INPUT,
            "Macro indicator adapter is not configured; supply indicators in options.",
            details={
                "required_inputs": ["macro_indicators"],
                "blocked_reasons": ["No macro indicator source was configured or supplied."],
                "data_status": "missing",
            },
            effect=SkillEffect.READ_EXTERNAL,
        )
    warnings = [f"macro indicator {index + 1} has no as_of timestamp." for index, item in enumerate(indicators) if not item.get("as_of")]
    return SkillOutput.ok(
        {
            "macro_indicators": indicators,
            "indicator_count": len(indicators),
            "data_status": "complete" if not warnings else "partial",
        },
        effect=SkillEffect.READ_EXTERNAL,
        warnings=warnings,
    )


def _analyze_sector_rotation(payload: SkillInput) -> SkillOutput:
    sectors = coerce_mapping_list(payload.options.get("sectors") or payload.options.get("sector_returns"))
    if not sectors:
        return missing_required_output(["sectors"], skill="analyze_sector_rotation")

    ranked = []
    for sector in sectors:
        name = normalize_text(sector.get("sector") or sector.get("name")) or "Unknown"
        value = decimal_to_float(sector.get("return") or sector.get("relative_return") or sector.get("performance")) or 0.0
        ranked.append({**sector, "sector": name, "rotation_score": value})
    ranked.sort(key=lambda item: item["rotation_score"], reverse=True)

    return SkillOutput.ok(
        {
            "leaders": ranked[:3],
            "laggards": list(reversed(ranked[-3:])),
            "ranked_sectors": ranked,
        }
    )


def _detect_risk_on_off(payload: SkillInput) -> SkillOutput:
    indicators = {normalize_text(row.get("name") or row.get("indicator")).casefold(): row for row in coerce_mapping_list(payload.options.get("indicators"))}
    inline = dict(payload.options.get("signals") or {})

    def signal_value(*names: str) -> float | None:
        for name in names:
            if name in inline:
                return decimal_to_float(inline.get(name))
            row = indicators.get(name.casefold())
            if row:
                return decimal_to_float(row.get("value") or row.get("level") or row.get("return"))
        return None

    equity_return = signal_value("equity_return", "sp500_return", "index_return") or 0.0
    vix = signal_value("vix", "volatility") or 20.0
    credit_spread = signal_value("credit_spread") or 0.0

    score = 0
    score += 1 if equity_return > 0 else -1 if equity_return < -0.01 else 0
    score += 1 if vix < 18 else -1 if vix > 25 else 0
    score += 1 if credit_spread <= 0 else -1 if credit_spread > 0.25 else 0

    if score >= 2:
        regime = "risk_on"
    elif score <= -2:
        regime = "risk_off"
    else:
        regime = "mixed"

    return SkillOutput.ok(
        {
            "regime": regime,
            "score": score,
            "signals": {
                "equity_return": equity_return,
                "vix": vix,
                "credit_spread": credit_spread,
            },
        }
    )


def _generate_market_brief(payload: SkillInput) -> SkillOutput:
    regime = payload.options.get("regime") or {}
    indices = coerce_mapping_list(payload.options.get("indices"))
    rotation = payload.options.get("rotation") or {}
    macro = coerce_mapping_list(payload.options.get("macro_indicators") or payload.options.get("macro"))

    if not regime and not indices and not rotation and not macro:
        return missing_required_output(["regime", "indices", "rotation", "macro_indicators"], skill="generate_market_brief")

    lines = ["# Market Brief", ""]
    if regime:
        label = regime.get("regime") if isinstance(regime, dict) else str(regime)
        lines.extend(["## Regime", "", f"- Current read: {label}"])
    if indices:
        lines.extend(["", "## Indices", ""])
        for item in indices[:8]:
            name = item.get("name") or item.get("ticker") or item.get("index") or "Index"
            value = item.get("value") or item.get("price") or item.get("level")
            change = item.get("change") or item.get("return")
            lines.append(f"- {name}: {value} ({change})")
    if rotation:
        leaders = rotation.get("leaders", []) if isinstance(rotation, dict) else []
        lines.extend(["", "## Sector Rotation", ""])
        lines.extend(f"- Leader: {item.get('sector')} ({item.get('rotation_score')})" for item in leaders[:3])
    if macro:
        lines.extend(["", "## Macro", ""])
        for item in macro[:8]:
            lines.append(f"- {item.get('name') or item.get('indicator')}: {item.get('value')}")

    brief = "\n".join(lines)
    return SkillOutput.ok(
        {
            "report_id": payload.options.get("report_id") or "market_brief_draft",
            "markdown": brief,
            "sections": ["regime", "indices", "sector_rotation", "macro"],
        }
    )
