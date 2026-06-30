"""LangGraph runtime helpers shared by all catalog skills."""

from __future__ import annotations

import hashlib
import json
import math
import operator
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from invest_llm_agents.common.enums import ErrorCode, SkillEffect
from invest_llm_agents.common.models import SourceRef
from invest_llm_agents.common.skill import SkillInput, SkillOutput


SkillHandler = Callable[[SkillInput], SkillOutput]


class SkillGraphState(TypedDict, total=False):
    skill_name: str
    skill_input: SkillInput
    output: SkillOutput
    current_node: str
    warnings: Annotated[list[str], operator.add]


def build_skill_graph(skill_name: str, handler: SkillHandler):
    """Build a two-node LangGraph wrapper for a single skill handler."""

    def validate_input(state: SkillGraphState) -> SkillGraphState:
        payload = state.get("skill_input")
        if payload is None:
            return {
                "current_node": "validate_input",
                "output": SkillOutput.blocked(
                    ErrorCode.MISSING_REQUIRED_INPUT,
                    "SkillInput payload is required.",
                    details={"skill": skill_name, "required_inputs": ["skill_input"]},
                ),
            }

        if not payload.run_id:
            return {
                "current_node": "validate_input",
                "output": SkillOutput.blocked(
                    ErrorCode.MISSING_REQUIRED_INPUT,
                    "run_id is required.",
                    details={"skill": skill_name, "required_inputs": ["run_id"]},
                ),
            }

        return {"current_node": "validate_input"}

    def execute_skill(state: SkillGraphState) -> SkillGraphState:
        existing = state.get("output")
        if existing is not None:
            return {"current_node": "execute_skill"}

        payload = state["skill_input"]
        try:
            output = handler(payload)
        except (ValueError, TypeError, InvalidOperation) as exc:
            output = SkillOutput.blocked(
                ErrorCode.INVALID_INPUT,
                str(exc),
                details={"skill": skill_name},
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            output = SkillOutput.blocked(
                ErrorCode.PARTIAL_EXTERNAL_OUTAGE,
                f"{skill_name} failed unexpectedly.",
                details={"exception_type": type(exc).__name__, "message": str(exc)},
            )

        return {"current_node": "execute_skill", "output": output}

    builder = StateGraph(SkillGraphState)
    builder.add_node("validate_input", validate_input)
    builder.add_node("execute_skill", execute_skill)
    builder.add_edge(START, "validate_input")
    builder.add_edge("validate_input", "execute_skill")
    builder.add_edge("execute_skill", END)
    return builder.compile()


def run_skill_graph(skill_name: str, payload: SkillInput, handler: SkillHandler) -> SkillOutput:
    """Invoke a catalog skill through LangGraph and return its SkillOutput."""
    graph = build_skill_graph(skill_name, handler)
    result = graph.invoke({"skill_name": skill_name, "skill_input": payload})
    output = result.get("output")
    if output is None:
        return SkillOutput.blocked(
            ErrorCode.PARTIAL_EXTERNAL_OUTAGE,
            f"{skill_name} did not produce SkillOutput.",
            details={"skill": skill_name},
        )
    return output


def require_options(payload: SkillInput, *names: str) -> list[str]:
    return [name for name in names if payload.options.get(name) in (None, "", [])]


def missing_required_output(names: list[str], *, skill: str) -> SkillOutput:
    return SkillOutput.needs_human_review(
        ErrorCode.MISSING_REQUIRED_INPUT,
        "Required skill inputs are missing.",
        details={"skill": skill, "required_inputs": names},
    )


def stable_id(prefix: str, value: Any) -> str:
    digest = hashlib.sha1(to_jsonable(value).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def decimal_to_float(value: Any) -> float | None:
    parsed = decimal_or_none(value)
    if parsed is None:
        return None
    if parsed.is_nan() or not math.isfinite(float(parsed)):
        return None
    return float(parsed)


def to_jsonable(value: Any) -> str:
    def default(obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json")
        if isinstance(obj, set):
            return sorted(obj)
        return str(obj)

    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=default)


def source_refs_from_payload(payload: SkillInput) -> list[SourceRef]:
    return payload.source_refs


def source_refs_to_dicts(source_refs: Sequence[SourceRef]) -> list[dict[str, Any]]:
    return [ref.model_dump(mode="json") for ref in source_refs]


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def tokenize(text: str) -> set[str]:
    return {token.casefold() for token in re.findall(r"[A-Za-z0-9_.$-]+", text)}


def lexical_score(query: str, text: str) -> float:
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0
    text_tokens = tokenize(text)
    if not text_tokens:
        return 0.0
    overlap = query_tokens & text_tokens
    return len(overlap) / len(query_tokens)


def coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def coerce_mapping_list(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in coerce_list(value):
        if hasattr(item, "model_dump"):
            rows.append(item.model_dump(mode="json"))
        elif isinstance(item, Mapping):
            rows.append(dict(item))
        else:
            rows.append({"value": item})
    return rows


def extract_body_text(options: Mapping[str, Any]) -> str:
    for key in ("text", "raw_text", "document_text", "body", "content"):
        text = normalize_text(options.get(key))
        if text:
            return text

    document = options.get("document")
    if isinstance(document, Mapping):
        return extract_body_text(document)
    return ""


def chunk_text(text: str, *, chunk_size: int = 1200, overlap: int = 150) -> list[dict[str, Any]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")
    if overlap < 0:
        raise ValueError("overlap must be zero or greater.")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size.")

    chunks: list[dict[str, Any]] = []
    start = 0
    index = 1
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(
                {
                    "index": index,
                    "text": chunk,
                    "page_or_offset": f"chars:{start}-{end}",
                }
            )
            index += 1
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def deterministic_embedding(text: str, *, dimensions: int = 16) -> list[float]:
    if dimensions <= 0:
        raise ValueError("dimensions must be greater than zero.")
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    for index in range(dimensions):
        byte = digest[index % len(digest)]
        values.append(round((byte / 255.0) * 2 - 1, 6))
    return values


def pick_first(options: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = options.get(name)
        if value not in (None, "", []):
            return value
    return None


def flatten_strings(values: Iterable[Any]) -> list[str]:
    flattened: list[str] = []
    for value in values:
        if isinstance(value, str):
            if value.strip():
                flattened.append(value.strip())
        elif isinstance(value, Mapping):
            text = pick_first(value, "text", "body", "title", "summary", "claim")
            if text:
                flattened.append(str(text).strip())
    return flattened
