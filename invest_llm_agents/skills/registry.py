"""Skill registry for catalog dispatch by name."""

from __future__ import annotations

from collections.abc import Callable

from invest_llm_agents.common.skill import SkillInput, SkillOutput
from invest_llm_agents.skills import data, knowledge, market, portfolio, rag, reports, verification


SkillCallable = Callable[[SkillInput], SkillOutput]


SKILL_REGISTRY: dict[str, SkillCallable] = {
    "parse_document": rag.parse_document,
    "chunk_document": rag.chunk_document,
    "embed_chunks": rag.embed_chunks,
    "retrieve_related_chunks": rag.retrieve_related_chunks,
    "rerank_context": rag.rerank_context,
    "normalize_ticker": portfolio.normalize_ticker,
    "fetch_price_data": portfolio.fetch_price_data,
    "calculate_returns": portfolio.calculate_returns,
    "calculate_weights": portfolio.calculate_weights,
    "detect_concentration": portfolio.detect_concentration,
    "extract_principles": knowledge.extract_principles,
    "extract_trade_patterns": knowledge.extract_trade_patterns,
    "link_rule_to_trade": knowledge.link_rule_to_trade,
    "detect_rule_conflict": knowledge.detect_rule_conflict,
    "create_wiki_revision": knowledge.create_wiki_revision,
    "verify_numbers": verification.verify_numbers,
    "verify_citations": verification.verify_citations,
    "check_unsupported_claims": verification.check_unsupported_claims,
    "check_recommendation_language": verification.check_recommendation_language,
    "check_stale_data": verification.check_stale_data,
    "assess_rag_confidence": verification.assess_rag_confidence,
    "quality_score": verification.quality_score,
    "generate_stock_snapshot": reports.generate_stock_snapshot,
    "generate_portfolio_report": reports.generate_portfolio_report,
    "generate_daily_check": reports.generate_daily_check,
    "generate_weekly_review": reports.generate_weekly_review,
    "format_persona_output": reports.format_persona_output,
    "fetch_news": data.fetch_news,
    "fetch_filings": data.fetch_filings,
    "fetch_financials": data.fetch_financials,
    "load_journal_entries": data.load_journal_entries,
    "load_current_holdings": data.load_current_holdings,
    "fetch_market_indices": market.fetch_market_indices,
    "fetch_macro_indicators": market.fetch_macro_indicators,
    "analyze_sector_rotation": market.analyze_sector_rotation,
    "detect_risk_on_off": market.detect_risk_on_off,
    "generate_market_brief": market.generate_market_brief,
}


def list_skills() -> list[str]:
    return sorted(SKILL_REGISTRY)


def invoke_skill(skill_name: str, payload: SkillInput) -> SkillOutput:
    try:
        skill = SKILL_REGISTRY[skill_name]
    except KeyError as exc:
        available = ", ".join(list_skills())
        raise KeyError(f"Unknown skill '{skill_name}'. Available skills: {available}") from exc
    return skill(payload)
