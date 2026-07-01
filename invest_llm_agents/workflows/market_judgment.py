"""Market judgment workflow graph built from catalog skills."""

from __future__ import annotations

from invest_llm_agents.common.skill import SkillInput, SkillOutput
from invest_llm_agents.workflows.base import (
    WorkflowState,
    aggregate_workflow_output,
    build_linear_workflow_graph,
    collect_staleness_items,
    invoke_step,
    report_to_text,
    run_workflow_graph,
    skipped_step,
    step_data,
)


def _fetch_market_indices(state: WorkflowState) -> WorkflowState:
    return invoke_step(state, "fetch_market_indices")


def _fetch_macro_indicators(state: WorkflowState) -> WorkflowState:
    return invoke_step(state, "fetch_macro_indicators")


def _analyze_sector_rotation(state: WorkflowState) -> WorkflowState:
    return invoke_step(state, "analyze_sector_rotation")


def _detect_risk_on_off(state: WorkflowState) -> WorkflowState:
    indicators = step_data(state, "fetch_macro_indicators").get("macro_indicators")
    return invoke_step(state, "detect_risk_on_off", options={"indicators": indicators})


def _generate_market_brief(state: WorkflowState) -> WorkflowState:
    return invoke_step(
        state,
        "generate_market_brief",
        options={
            "indices": step_data(state, "fetch_market_indices").get("indices"),
            "macro_indicators": step_data(state, "fetch_macro_indicators").get("macro_indicators"),
            "rotation": step_data(state, "analyze_sector_rotation"),
            "regime": step_data(state, "detect_risk_on_off"),
        },
    )


def _check_stale_data(state: WorkflowState) -> WorkflowState:
    items = collect_staleness_items(
        step_data(state, "fetch_market_indices").get("indices"),
        step_data(state, "fetch_macro_indicators").get("macro_indicators"),
    )
    if not items:
        return skipped_step("check_stale_data", "No timestamped market data was available.")
    return invoke_step(state, "check_stale_data", options={"items": items})


def _check_recommendation_language(state: WorkflowState) -> WorkflowState:
    text = report_to_text({"sections": [{"title": "Market Brief", "body": step_data(state, "generate_market_brief").get("markdown")}]})
    if not text.strip():
        return skipped_step("check_recommendation_language", "No generated market brief was available.")
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
        workflow_name="market_judgment",
        state=state,
        data={
            "brief": step_data(state, "generate_market_brief"),
            "regime": step_data(state, "detect_risk_on_off"),
            "rotation": step_data(state, "analyze_sector_rotation"),
            "quality": step_data(state, "quality_score"),
            "verification": {
                "staleness": step_data(state, "check_stale_data"),
                "language": step_data(state, "check_recommendation_language"),
            },
        },
    )
    return {"final_output": output}


def build_market_judgment_graph():
    return build_linear_workflow_graph(
        [
            ("fetch_market_indices", _fetch_market_indices),
            ("fetch_macro_indicators", _fetch_macro_indicators),
            ("analyze_sector_rotation", _analyze_sector_rotation),
            ("detect_risk_on_off", _detect_risk_on_off),
            ("generate_market_brief", _generate_market_brief),
            ("check_stale_data", _check_stale_data),
            ("check_recommendation_language", _check_recommendation_language),
            ("quality_score", _quality_score),
            ("finalize", _finalize),
        ]
    )


def run_market_judgment(payload: SkillInput) -> SkillOutput:
    return run_workflow_graph(build_market_judgment_graph(), payload)
