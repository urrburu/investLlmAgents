"""Knowledge extraction catalog skills implemented with LangGraph."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from invest_llm_agents.common.enums import ErrorCode, SkillEffect
from invest_llm_agents.common.skill import SkillInput, SkillOutput
from invest_llm_agents.skills.base import (
    coerce_mapping_list,
    extract_body_text,
    lexical_score,
    missing_required_output,
    normalize_text,
    run_skill_graph,
    source_refs_from_payload,
    source_refs_to_dicts,
    stable_id,
    tokenize,
    utc_now,
)
from invest_llm_agents.skills.storage import redact_database_url, resolve_database_url, upsert_wiki_revision


def extract_principles(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("extract_principles", payload, _extract_principles)


def extract_trade_patterns(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("extract_trade_patterns", payload, _extract_trade_patterns)


def link_rule_to_trade(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("link_rule_to_trade", payload, _link_rule_to_trade)


def detect_rule_conflict(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("detect_rule_conflict", payload, _detect_rule_conflict)


def create_wiki_revision(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("create_wiki_revision", payload, _create_wiki_revision)


PRINCIPLE_MARKERS = (
    "principle",
    "rule",
    "must",
    "should",
    "avoid",
    "never",
    "always",
    "discipline",
    "risk",
)


def _sentence_split(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]


def _extract_principles(payload: SkillInput) -> SkillOutput:
    text = extract_body_text(payload.options)
    if not text:
        return missing_required_output(["text"], skill="extract_principles")

    principles = []
    for sentence in _sentence_split(text):
        lowered = sentence.casefold()
        if any(marker in lowered for marker in PRINCIPLE_MARKERS):
            principles.append(
                {
                    "principle_id": stable_id("principle", sentence),
                    "text": sentence,
                    "confidence": "medium",
                    "source_refs": source_refs_to_dicts(source_refs_from_payload(payload)),
                }
            )

    if not principles:
        principles.append(
            {
                "principle_id": stable_id("principle", text[:200]),
                "text": text[:300],
                "confidence": "low",
                "source_refs": source_refs_to_dicts(source_refs_from_payload(payload)),
            }
        )

    return SkillOutput.ok({"principles": principles, "principle_count": len(principles)})


def _extract_trade_patterns(payload: SkillInput) -> SkillOutput:
    entries = coerce_mapping_list(payload.options.get("journal_entries") or payload.options.get("trades"))
    if not entries:
        return missing_required_output(["journal_entries"], skill="extract_trade_patterns")

    grouped: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        ticker = normalize_text(entry.get("ticker")).upper() or "UNKNOWN"
        action = normalize_text(entry.get("action") or entry.get("side")).casefold() or "unknown"
        grouped[(ticker, action)].append(entry)

    patterns = []
    for (ticker, action), rows in grouped.items():
        reasons = Counter(normalize_text(row.get("reason") or row.get("rationale")) for row in rows)
        reasons.pop("", None)
        outcomes = [float(row.get("return") or row.get("pnl_pct") or 0) for row in rows]
        avg_outcome = sum(outcomes) / len(outcomes) if outcomes else 0.0
        patterns.append(
            {
                "pattern_id": stable_id("trade_pattern", {"ticker": ticker, "action": action, "count": len(rows)}),
                "ticker": ticker,
                "action": action,
                "trade_count": len(rows),
                "common_reasons": [reason for reason, _ in reasons.most_common(3)],
                "average_return": round(avg_outcome, 6),
            }
        )

    return SkillOutput.ok({"patterns": patterns, "pattern_count": len(patterns)})


def _link_rule_to_trade(payload: SkillInput) -> SkillOutput:
    rules = coerce_mapping_list(payload.options.get("rules") or payload.options.get("principles"))
    trades = coerce_mapping_list(payload.options.get("trades") or payload.options.get("journal_entries"))
    if not rules or not trades:
        return missing_required_output(["rules", "trades"], skill="link_rule_to_trade")

    links = []
    for rule in rules:
        rule_text = normalize_text(rule.get("text") or rule.get("body") or rule.get("rule"))
        rule_id = rule.get("rule_id") or rule.get("principle_id") or stable_id("rule", rule_text)
        for trade in trades:
            trade_text = " ".join(
                normalize_text(trade.get(key))
                for key in ("ticker", "action", "reason", "rationale", "notes")
                if trade.get(key)
            )
            score = lexical_score(rule_text, trade_text)
            if score > 0:
                links.append(
                    {
                        "link_id": stable_id("rule_trade_link", {"rule_id": rule_id, "trade": trade, "score": score}),
                        "rule_id": rule_id,
                        "trade_id": trade.get("trade_id") or stable_id("trade", trade),
                        "score": round(score, 6),
                    }
                )

    links.sort(key=lambda item: item["score"], reverse=True)
    return SkillOutput.ok({"links": links, "link_count": len(links)})


CONFLICT_PAIRS = (
    ("always", "never"),
    ("must buy", "must not buy"),
    ("buy", "avoid"),
    ("increase", "reduce"),
    ("concentrate", "diversify"),
)


def _detect_rule_conflict(payload: SkillInput) -> SkillOutput:
    rules = coerce_mapping_list(payload.options.get("rules") or payload.options.get("principles"))
    if not rules:
        return missing_required_output(["rules"], skill="detect_rule_conflict")

    conflicts = []
    for index, left in enumerate(rules):
        left_text = normalize_text(left.get("text") or left.get("body") or left.get("rule"))
        left_tokens = tokenize(left_text)
        for right in rules[index + 1 :]:
            right_text = normalize_text(right.get("text") or right.get("body") or right.get("rule"))
            right_tokens = tokenize(right_text)
            overlap = left_tokens & right_tokens
            if not overlap:
                continue
            for positive, negative in CONFLICT_PAIRS:
                if positive in left_text.casefold() and negative in right_text.casefold():
                    conflicts.append(_conflict_record(left, right, positive, negative, overlap))
                elif negative in left_text.casefold() and positive in right_text.casefold():
                    conflicts.append(_conflict_record(left, right, negative, positive, overlap))

    return SkillOutput.ok({"conflicts": conflicts, "conflict_count": len(conflicts)})


def _conflict_record(left: dict[str, Any], right: dict[str, Any], left_phrase: str, right_phrase: str, overlap: set[str]) -> dict[str, Any]:
    left_id = left.get("rule_id") or left.get("principle_id") or stable_id("rule", left)
    right_id = right.get("rule_id") or right.get("principle_id") or stable_id("rule", right)
    return {
        "conflict_id": stable_id("rule_conflict", {"left": left_id, "right": right_id}),
        "left_rule_id": left_id,
        "right_rule_id": right_id,
        "reason": f"Potential conflict between '{left_phrase}' and '{right_phrase}'.",
        "shared_terms": sorted(overlap),
    }


def _create_wiki_revision(payload: SkillInput) -> SkillOutput:
    proposed_body = normalize_text(payload.options.get("proposed_body") or payload.options.get("body"))
    if not proposed_body:
        principles = coerce_mapping_list(payload.options.get("principles"))
        patterns = coerce_mapping_list(payload.options.get("patterns"))
        lines = [normalize_text(item.get("text") or item.get("summary") or item) for item in [*principles, *patterns]]
        proposed_body = "\n".join(line for line in lines if line)

    if not proposed_body:
        return missing_required_output(["proposed_body", "principles", "patterns"], skill="create_wiki_revision")

    page_id = payload.options.get("page_id") or stable_id("wiki_page", proposed_body[:120])
    revision_id = payload.options.get("revision_id") or stable_id(
        "wiki_revision",
        {"page_id": page_id, "body": proposed_body, "run_id": payload.run_id},
    )
    revision = {
        "revision_id": revision_id,
        "page_id": page_id,
        "operation": payload.options.get("operation") or "update",
        "change_summary": payload.options.get("change_summary") or "Proposed wiki update from extracted knowledge.",
        "before_refs": payload.options.get("before_refs") or [],
        "after_refs": payload.options.get("after_refs") or [],
        "diff_summary": payload.options.get("diff_summary") or "Review proposed_body before accepting.",
        "proposed_body": proposed_body,
        "source_refs": source_refs_to_dicts(source_refs_from_payload(payload)),
        "status": "draft",
        "created_by_agent": payload.options.get("created_by_agent") or "skill:create_wiki_revision",
        "created_at": utc_now().isoformat(),
    }
    page = {
        "page_id": page_id,
        "namespace": payload.options.get("namespace") or "/wiki/drafts",
        "page_type": payload.options.get("page_type") or "principle",
        "title": payload.options.get("title") or revision["change_summary"],
        "body": payload.options.get("existing_body") or "",
        "source_refs": revision["source_refs"],
        "confidence": payload.options.get("confidence") or "low",
        "open_questions": payload.options.get("open_questions") or [],
    }
    database_url = resolve_database_url(payload.options)
    persistence = None
    warnings = []
    if payload.options.get("persist"):
        if database_url:
            try:
                persistence = upsert_wiki_revision(database_url=database_url, revision=revision, page=page)
            except Exception as exc:
                return SkillOutput.needs_human_review(
                    ErrorCode.PARTIAL_EXTERNAL_OUTAGE,
                    "Wiki revision persistence failed.",
                    details={"exception_type": type(exc).__name__, "message": str(exc)},
                    data={
                        "revision": revision,
                        "page": page,
                        "revision_id": revision_id,
                        "persistence": None,
                        "database_url": redact_database_url(database_url),
                        "write_log": {
                            "effect": SkillEffect.PROPOSE_REVISION.value,
                            "input_summary": {
                                "page_id": page_id,
                                "operation": revision["operation"],
                                "source_ref_count": len(revision["source_refs"]),
                                "proposed_body_chars": len(proposed_body),
                            },
                            "target_tables": ["wiki_pages", "wiki_revisions"],
                            "row_ids": {},
                            "rollback": "No rollback is required if the transaction failed before commit.",
                        },
                    },
                    effect=SkillEffect.PROPOSE_REVISION,
                    warnings=warnings,
                )
        else:
            warnings.append("Revision persistence was requested, but INVEST_LLM_DATABASE_URL/database_url was not supplied.")

    write_log = {
        "effect": SkillEffect.PROPOSE_REVISION.value,
        "input_summary": {
            "page_id": page_id,
            "operation": revision["operation"],
            "source_ref_count": len(revision["source_refs"]),
            "proposed_body_chars": len(proposed_body),
        },
        "target_tables": ["wiki_pages", "wiki_revisions"] if persistence else [],
        "row_ids": persistence or {},
        "rollback": "Set wiki_revisions.status='rejected' for the revision_id; do not update wiki_pages.body until accepted.",
    }
    return SkillOutput.ok(
        {
            "revision": revision,
            "page": page,
            "revision_id": revision_id,
            "persistence": persistence,
            "database_url": redact_database_url(database_url),
            "write_log": write_log,
        },
        effect=SkillEffect.PROPOSE_REVISION,
        warnings=warnings,
    )
