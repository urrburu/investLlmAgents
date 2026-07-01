"""Shared helpers for multi-skill LangGraph workflows."""

from __future__ import annotations

import operator
from collections.abc import Callable, Iterable, Sequence
from typing import Annotated, Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from invest_llm_agents.common.enums import ErrorCode, SkillEffect, SkillStatus
from invest_llm_agents.common.models import SourceRef
from invest_llm_agents.common.skill import SkillInput, SkillOutput


def merge_step_outputs(
    left: dict[str, SkillOutput] | None,
    right: dict[str, SkillOutput] | None,
) -> dict[str, SkillOutput]:
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class WorkflowState(TypedDict, total=False):
    run_id: str
    options: dict[str, Any]
    source_refs: list[SourceRef]
    step_outputs: Annotated[dict[str, SkillOutput], merge_step_outputs]
    warnings: Annotated[list[str], operator.add]
    final_output: SkillOutput


WorkflowNode = Callable[[WorkflowState], WorkflowState]


def build_linear_workflow_graph(nodes: Sequence[tuple[str, WorkflowNode]]):
    builder = StateGraph(WorkflowState)
    previous = START
    for node_name, node in nodes:
        builder.add_node(node_name, node)
        builder.add_edge(previous, node_name)
        previous = node_name
    builder.add_edge(previous, END)
    return builder.compile()


def run_workflow_graph(graph: Any, payload: SkillInput) -> SkillOutput:
    if not payload.run_id:
        return SkillOutput.blocked(
            ErrorCode.MISSING_REQUIRED_INPUT,
            "run_id is required.",
            details={"required_inputs": ["run_id"]},
        )

    result = graph.invoke(
        {
            "run_id": payload.run_id,
            "options": dict(payload.options),
            "source_refs": list(payload.source_refs),
            "step_outputs": {},
            "warnings": [],
        }
    )
    output = result.get("final_output")
    if output is None:
        return SkillOutput.blocked(
            ErrorCode.PARTIAL_EXTERNAL_OUTAGE,
            "Workflow did not produce SkillOutput.",
        )
    return output


def invoke_step(
    state: WorkflowState,
    skill_name: str,
    *,
    options: dict[str, Any] | None = None,
    step_name: str | None = None,
) -> WorkflowState:
    from invest_llm_agents.skills import invoke_skill

    merged_options = {**dict(state.get("options") or {}), **dict(options or {})}
    payload = SkillInput(
        run_id=state["run_id"],
        source_refs=list(state.get("source_refs") or []),
        options=merged_options,
    )
    output = invoke_skill(skill_name, payload)
    key = step_name or skill_name
    return {
        "step_outputs": {key: output},
        "warnings": [f"{key}: {warning}" for warning in output.warnings],
    }


def skipped_step(step_name: str, reason: str) -> WorkflowState:
    return {"step_outputs": {step_name: SkillOutput.ok({"skipped": True, "reason": reason})}}


def step_output(state: WorkflowState, step_name: str) -> SkillOutput | None:
    return (state.get("step_outputs") or {}).get(step_name)


def step_data(state: WorkflowState, step_name: str) -> dict[str, Any]:
    output = step_output(state, step_name)
    return dict(output.data) if output is not None else {}


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", []):
            return value
    return None


def coerce_rows(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    elif isinstance(value, tuple):
        items = list(value)
    else:
        items = [value]

    rows: list[dict[str, Any]] = []
    for item in items:
        if hasattr(item, "model_dump"):
            rows.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            rows.append(dict(item))
        else:
            rows.append({"value": item})
    return rows


def report_to_text(report: dict[str, Any]) -> str:
    sections = coerce_rows(report.get("sections"))
    if sections:
        return "\n\n".join(
            f"## {section.get('title')}\n{section.get('body')}"
            for section in sections
            if section.get("title") or section.get("body")
        )
    return str(report) if report else ""


def collect_staleness_items(*collections: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for collection in collections:
        for row in coerce_rows(collection):
            if any(row.get(key) for key in ("as_of", "published_at", "timestamp")):
                items.append(row)
    return items


_EFFECT_PRIORITY = {
    SkillEffect.PURE: 0,
    SkillEffect.READ_EXTERNAL: 1,
    SkillEffect.PROPOSE_REVISION: 2,
    SkillEffect.WRITE_INTERNAL: 3,
}


def combine_effect(outputs: Iterable[SkillOutput]) -> SkillEffect:
    effect = SkillEffect.PURE
    for output in outputs:
        current = SkillEffect(output.effect)
        if _EFFECT_PRIORITY[current] > _EFFECT_PRIORITY[effect]:
            effect = current
    return effect


def collect_source_refs(outputs: Iterable[SkillOutput]) -> list[SourceRef]:
    refs: list[SourceRef] = []
    seen: set[str] = set()
    for output in outputs:
        for ref in output.source_refs:
            key = ref.model_dump_json()
            if key not in seen:
                refs.append(ref)
                seen.add(key)
    return refs


def output_json(output: SkillOutput) -> dict[str, Any]:
    return output.model_dump(mode="json")


def aggregate_workflow_output(
    *,
    workflow_name: str,
    state: WorkflowState,
    data: dict[str, Any],
) -> SkillOutput:
    step_outputs = dict(state.get("step_outputs") or {})
    outputs = list(step_outputs.values())
    warnings = list(state.get("warnings") or [])
    errors = {
        step_name: output.error.model_dump(mode="json")
        for step_name, output in step_outputs.items()
        if output.error is not None
    }
    blocked_steps = [
        step_name
        for step_name, output in step_outputs.items()
        if output.status in {SkillStatus.BLOCKED, SkillStatus.FAILED}
    ]
    review_steps = [
        step_name
        for step_name, output in step_outputs.items()
        if output.status == SkillStatus.NEEDS_HUMAN_REVIEW
    ]
    partial_steps = [
        step_name
        for step_name, output in step_outputs.items()
        if output.status == SkillStatus.PARTIAL
    ]

    payload = {
        "workflow": workflow_name,
        **data,
        "steps": list(step_outputs),
        "step_outputs": {name: output_json(output) for name, output in step_outputs.items()},
        "errors": errors,
    }
    effect = combine_effect(outputs)
    source_refs = collect_source_refs(outputs)

    if blocked_steps:
        first_error = step_outputs[blocked_steps[0]].error
        return SkillOutput.blocked(
            first_error.error_code if first_error else ErrorCode.PARTIAL_EXTERNAL_OUTAGE,
            f"{workflow_name} has blocked step(s).",
            details={"blocked_steps": blocked_steps, "review_steps": review_steps},
            data=payload,
            effect=effect,
            source_refs=source_refs,
            warnings=warnings,
        )
    if review_steps:
        first_error = step_outputs[review_steps[0]].error
        return SkillOutput.needs_human_review(
            first_error.error_code if first_error else ErrorCode.MISSING_REQUIRED_INPUT,
            f"{workflow_name} needs human review.",
            details={"review_steps": review_steps},
            data=payload,
            effect=effect,
            source_refs=source_refs,
            warnings=warnings,
        )
    if partial_steps:
        return SkillOutput.partial(payload, effect=effect, source_refs=source_refs, warnings=warnings)
    return SkillOutput.ok(payload, effect=effect, source_refs=source_refs, warnings=warnings)
