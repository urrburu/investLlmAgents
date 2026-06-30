"""Report generation catalog skills implemented with LangGraph."""

from __future__ import annotations

from typing import Any

from invest_llm_agents.common.enums import ErrorCode, ReportType, SkillEffect, VerificationStatus
from invest_llm_agents.common.skill import SkillInput, SkillOutput
from invest_llm_agents.skills.base import coerce_mapping_list, missing_required_output, normalize_text, run_skill_graph, stable_id, utc_now
from invest_llm_agents.skills.storage import redact_database_url, resolve_database_url, upsert_report_draft


def generate_stock_snapshot(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("generate_stock_snapshot", payload, _generate_stock_snapshot)


def generate_portfolio_report(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("generate_portfolio_report", payload, _generate_portfolio_report)


def generate_daily_check(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("generate_daily_check", payload, _generate_daily_check)


def generate_weekly_review(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("generate_weekly_review", payload, _generate_weekly_review)


def format_persona_output(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("format_persona_output", payload, _format_persona_output)


def _section(section_id: str, title: str, body: str, order: int) -> dict[str, Any]:
    return {
        "section_id": section_id,
        "title": title,
        "status": VerificationStatus.PENDING,
        "display_order": order,
        "body": body,
        "source_refs": [],
    }


def _report(report_type: ReportType, title: str, sections: list[dict[str, Any]], payload: SkillInput) -> dict[str, Any]:
    report_id = payload.options.get("report_id") or stable_id(
        "report",
        {"run_id": payload.run_id, "report_type": report_type.value, "title": title, "sections": sections},
    )
    return {
        "report_id": report_id,
        "report_type": report_type.value,
        "title": title,
        "as_of": (payload.options.get("as_of") or utc_now().isoformat()),
        "sections": sections,
        "claims": payload.options.get("claims") or [],
        "numbers": payload.options.get("numbers") or [],
        "source_refs": [ref.model_dump(mode="json") for ref in payload.source_refs],
        "actions": payload.options.get("actions") or [],
        "verification_status": VerificationStatus.PENDING,
    }


def _report_output(report: dict[str, Any], payload: SkillInput) -> SkillOutput:
    database_url = resolve_database_url(payload.options)
    persistence = None
    warnings = []
    if payload.options.get("persist"):
        if database_url:
            try:
                persistence = upsert_report_draft(database_url=database_url, report=report)
            except Exception as exc:
                return SkillOutput.needs_human_review(
                    ErrorCode.PARTIAL_EXTERNAL_OUTAGE,
                    "Report draft persistence failed.",
                    details={"exception_type": type(exc).__name__, "message": str(exc)},
                    data={
                        "report": report,
                        "report_id": report["report_id"],
                        "persistence": None,
                        "database_url": redact_database_url(database_url),
                        "write_log": {
                            "effect": SkillEffect.WRITE_INTERNAL.value,
                            "input_summary": {
                                "report_id": report["report_id"],
                                "report_type": report["report_type"],
                                "section_count": len(report.get("sections") or []),
                                "verification_status": str(report.get("verification_status")),
                            },
                            "target_tables": ["report_drafts"],
                            "row_ids": {},
                            "rollback": "No rollback is required if the transaction failed before commit.",
                        },
                    },
                    effect=SkillEffect.WRITE_INTERNAL,
                    warnings=warnings,
                )
        else:
            warnings.append("Report persistence was requested, but INVEST_LLM_DATABASE_URL/database_url was not supplied.")

    effect = SkillEffect.WRITE_INTERNAL if persistence else SkillEffect.PURE
    return SkillOutput.ok(
        {
            "report": report,
            "report_id": report["report_id"],
            "persistence": persistence,
            "database_url": redact_database_url(database_url),
            "write_log": {
                "effect": effect.value,
                "input_summary": {
                    "report_id": report["report_id"],
                    "report_type": report["report_type"],
                    "section_count": len(report.get("sections") or []),
                    "verification_status": str(report.get("verification_status")),
                },
                "target_tables": ["report_drafts"] if persistence else [],
                "row_ids": persistence or {},
                "rollback": "Delete or supersede report_drafts by report_id; never promote unless verification_status is passed.",
            },
        },
        effect=effect,
        warnings=warnings,
    )


def _generate_stock_snapshot(payload: SkillInput) -> SkillOutput:
    ticker = normalize_text(payload.options.get("ticker")).upper()
    if not ticker:
        return missing_required_output(["ticker"], skill="generate_stock_snapshot")

    price_data = payload.options.get("price_data") or payload.options.get("prices") or {}
    financials = payload.options.get("financials") or {}
    news = coerce_mapping_list(payload.options.get("news"))
    sections = [
        _section("snapshot_summary", "Snapshot Summary", f"{ticker} snapshot draft based on supplied data.", 1),
        _section("price", "Price", str(price_data or "No price data supplied."), 2),
        _section("financials", "Financials", str(financials or "No financial data supplied."), 3),
        _section("recent_news", "Recent News", "\n".join(str(item) for item in news[:5]) or "No news supplied.", 4),
    ]
    report = _report(ReportType.STOCK_SNAPSHOT, f"{ticker} Snapshot", sections, payload)
    return _report_output(report, payload)


def _generate_portfolio_report(payload: SkillInput) -> SkillOutput:
    holdings = coerce_mapping_list(payload.options.get("holdings"))
    if not holdings:
        return missing_required_output(["holdings"], skill="generate_portfolio_report")

    metrics = payload.options.get("metrics") or {}
    concentration = payload.options.get("concentration") or {}
    sections = [
        _section("portfolio_overview", "Portfolio Overview", f"{len(holdings)} holdings in current snapshot.", 1),
        _section("weights", "Weights", str(metrics.get("holdings") or holdings), 2),
        _section("concentration", "Concentration", str(concentration or "No concentration flags supplied."), 3),
    ]
    report = _report(ReportType.PORTFOLIO_REPORT, "Portfolio Report", sections, payload)
    return _report_output(report, payload)


def _generate_daily_check(payload: SkillInput) -> SkillOutput:
    market_brief = normalize_text(payload.options.get("market_brief") or payload.options.get("market_summary"))
    portfolio_summary = normalize_text(payload.options.get("portfolio_summary"))
    alerts = coerce_mapping_list(payload.options.get("alerts"))
    if not market_brief and not portfolio_summary and not alerts:
        return missing_required_output(["market_brief", "portfolio_summary", "alerts"], skill="generate_daily_check")

    sections = [
        _section("market", "Market", market_brief or "No market brief supplied.", 1),
        _section("portfolio", "Portfolio", portfolio_summary or "No portfolio summary supplied.", 2),
        _section("alerts", "Alerts", "\n".join(str(alert) for alert in alerts) or "No alerts.", 3),
    ]
    report = _report(ReportType.DAILY_CHECK, "Daily Check", sections, payload)
    return _report_output(report, payload)


def _generate_weekly_review(payload: SkillInput) -> SkillOutput:
    journal_entries = coerce_mapping_list(payload.options.get("journal_entries"))
    portfolio_report = payload.options.get("portfolio_report")
    lessons = coerce_mapping_list(payload.options.get("lessons") or payload.options.get("principles"))
    if not journal_entries and not portfolio_report and not lessons:
        return missing_required_output(["journal_entries", "portfolio_report", "lessons"], skill="generate_weekly_review")

    sections = [
        _section("trades", "Trades", f"{len(journal_entries)} journal entries reviewed.", 1),
        _section("portfolio", "Portfolio", str(portfolio_report or "No portfolio report supplied."), 2),
        _section("lessons", "Lessons", "\n".join(str(item) for item in lessons) or "No lessons supplied.", 3),
    ]
    report = _report(ReportType.WEEKLY_REVIEW, "Weekly Review", sections, payload)
    return _report_output(report, payload)


def _format_persona_output(payload: SkillInput) -> SkillOutput:
    text = normalize_text(payload.options.get("text") or payload.options.get("markdown"))
    report = payload.options.get("report")
    persona = normalize_text(payload.options.get("persona") or "analyst").casefold()
    if not text and isinstance(report, dict):
        sections = coerce_mapping_list(report.get("sections"))
        text = "\n\n".join(f"## {section.get('title')}\n{section.get('body')}" for section in sections)
    if not text:
        return missing_required_output(["text", "report"], skill="format_persona_output")

    headings = {
        "analyst": "Analyst View",
        "coach": "Process Coach",
        "risk": "Risk Review",
    }
    title = headings.get(persona, "Persona View")
    formatted = f"# {title}\n\n{text}"
    from invest_llm_agents.common.verification import check_recommendation_language

    language_checks = check_recommendation_language(formatted)
    if language_checks:
        return SkillOutput.blocked(
            ErrorCode.UNSUPPORTED_RECOMMENDATION,
            "Persona formatting output contains prohibited recommendation language.",
            details={"language_checks": language_checks},
            data={"persona": persona, "markdown": formatted},
        )

    return SkillOutput.ok({"persona": persona, "markdown": formatted, "language_checks": []})
