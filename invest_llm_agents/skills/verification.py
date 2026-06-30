"""Verification catalog skills implemented as LangGraph-backed callables."""

from __future__ import annotations

from datetime import timezone
from typing import Any

from invest_llm_agents.common.enums import ErrorCode, SkillEffect, VerificationStatus
from invest_llm_agents.common.skill import SkillInput, SkillOutput
from invest_llm_agents.common.verification import check_recommendation_language as common_language_check
from invest_llm_agents.skills.base import (
    coerce_mapping_list,
    decimal_or_none,
    flatten_strings,
    lexical_score,
    missing_required_output,
    normalize_text,
    parse_datetime,
    run_skill_graph,
    stable_id,
    utc_now,
)


def verify_numbers(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("verify_numbers", payload, _verify_numbers)


def verify_citations(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("verify_citations", payload, _verify_citations)


def check_unsupported_claims(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("check_unsupported_claims", payload, _check_unsupported_claims)


def check_recommendation_language(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("check_recommendation_language", payload, _check_recommendation_language)


def check_stale_data(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("check_stale_data", payload, _check_stale_data)


def assess_rag_confidence(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("assess_rag_confidence", payload, _assess_rag_confidence)


def quality_score(payload: SkillInput) -> SkillOutput:
    return run_skill_graph("quality_score", payload, _quality_score)


def _verify_numbers(payload: SkillInput) -> SkillOutput:
    numbers = coerce_mapping_list(payload.options.get("numbers"))
    if not numbers:
        return missing_required_output(["numbers"], skill="verify_numbers")

    tolerance = decimal_or_none(payload.options.get("tolerance")) or decimal_or_none("0.0001")
    checks = []
    mismatches = []
    for number in numbers:
        actual = decimal_or_none(number.get("value") or number.get("actual"))
        expected = decimal_or_none(number.get("expected") or number.get("source_value"))
        number_id = number.get("number_id") or stable_id("number", number)
        if actual is None or expected is None:
            checks.append(
                {
                    "number_id": number_id,
                    "status": VerificationStatus.NEEDS_HUMAN_REVIEW,
                    "message": "Actual and expected values are required for numeric verification.",
                }
            )
            continue
        delta = abs(actual - expected)
        passed = delta <= tolerance
        check = {
            "number_id": number_id,
            "status": VerificationStatus.PASSED if passed else VerificationStatus.BLOCKED,
            "actual": str(actual),
            "expected": str(expected),
            "delta": str(delta),
            "tolerance": str(tolerance),
            "formula": number.get("formula"),
        }
        checks.append(check)
        if not passed:
            mismatches.append(number_id)

    status = VerificationStatus.BLOCKED if mismatches else VerificationStatus.PASSED
    return SkillOutput.ok({"status": status, "number_checks": checks, "mismatches": mismatches})


def _verify_citations(payload: SkillInput) -> SkillOutput:
    claims = coerce_mapping_list(payload.options.get("claims"))
    if not claims:
        return missing_required_output(["claims"], skill="verify_citations")

    checks = []
    missing = []
    for claim in claims:
        claim_id = claim.get("claim_id") or stable_id("claim", claim)
        refs = claim.get("source_refs") or claim.get("citations") or []
        passed = bool(refs)
        checks.append(
            {
                "claim_id": claim_id,
                "status": VerificationStatus.PASSED if passed else VerificationStatus.NEEDS_HUMAN_REVIEW,
                "citation_count": len(refs),
                "error_code": None if passed else ErrorCode.MISSING_CITATION,
            }
        )
        if not passed:
            missing.append(claim_id)

    status = VerificationStatus.NEEDS_HUMAN_REVIEW if missing else VerificationStatus.PASSED
    return SkillOutput.ok({"status": status, "citation_checks": checks, "missing_citations": missing})


UNSUPPORTED_MARKERS = (
    "definitely",
    "certainly",
    "guaranteed",
    "cannot lose",
    "will outperform",
    "risk-free",
)


def _check_unsupported_claims(payload: SkillInput) -> SkillOutput:
    claims = coerce_mapping_list(payload.options.get("claims"))
    if not claims:
        return missing_required_output(["claims"], skill="check_unsupported_claims")

    checks = []
    unsupported = []
    for claim in claims:
        text = normalize_text(claim.get("text") or claim.get("claim"))
        refs = claim.get("source_refs") or claim.get("citations") or []
        matched = [marker for marker in UNSUPPORTED_MARKERS if marker in text.casefold()]
        missing_refs = not refs
        status = VerificationStatus.PASSED
        if matched or missing_refs:
            status = VerificationStatus.NEEDS_REVISION
            unsupported.append(claim.get("claim_id") or stable_id("claim", claim))
        checks.append(
            {
                "claim_id": claim.get("claim_id") or stable_id("claim", claim),
                "status": status,
                "matched_markers": matched,
                "has_source_refs": bool(refs),
            }
        )

    status = VerificationStatus.NEEDS_REVISION if unsupported else VerificationStatus.PASSED
    return SkillOutput.ok({"status": status, "unsupported_claim_checks": checks, "unsupported_claims": unsupported})


LOCAL_FORBIDDEN_PHRASES = (
    "buy now",
    "sell now",
    "must buy",
    "must sell",
    "price target is",
    "guaranteed return",
)


def _check_recommendation_language(payload: SkillInput) -> SkillOutput:
    text = normalize_text(payload.options.get("text"))
    if not text:
        claims = flatten_strings(payload.options.get("claims") or [])
        sections = flatten_strings(payload.options.get("sections") or [])
        text = "\n".join([*claims, *sections])
    if not text:
        return missing_required_output(["text"], skill="check_recommendation_language")

    checks = common_language_check(text)
    lowered = text.casefold()
    for phrase in LOCAL_FORBIDDEN_PHRASES:
        if phrase in lowered:
            checks.append(
                {
                    "status": VerificationStatus.BLOCKED,
                    "error_code": ErrorCode.UNSUPPORTED_RECOMMENDATION,
                    "matched_phrase": phrase,
                    "message": "Direct buy/sell recommendation language is not allowed.",
                }
            )

    status = VerificationStatus.BLOCKED if checks else VerificationStatus.PASSED
    return SkillOutput.ok({"status": status, "language_checks": checks})


def _check_stale_data(payload: SkillInput) -> SkillOutput:
    items = coerce_mapping_list(payload.options.get("items") or payload.options.get("source_refs"))
    if not items:
        return missing_required_output(["items"], skill="check_stale_data")

    max_age_days = int(payload.options.get("max_age_days", 7))
    now = parse_datetime(payload.options.get("now")) or utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    checks = []
    stale = []
    for item in items:
        as_of = parse_datetime(item.get("as_of") or item.get("published_at") or item.get("timestamp"))
        item_id = item.get("source_id") or item.get("id") or stable_id("source", item)
        if as_of is None:
            checks.append(
                {
                    "source_id": item_id,
                    "status": VerificationStatus.NEEDS_HUMAN_REVIEW,
                    "message": "No as_of timestamp supplied.",
                }
            )
            stale.append(item_id)
            continue
        age_days = (now - as_of).total_seconds() / 86400
        passed = age_days <= max_age_days
        checks.append(
            {
                "source_id": item_id,
                "status": VerificationStatus.PASSED if passed else VerificationStatus.BLOCKED,
                "age_days": round(age_days, 3),
                "max_age_days": max_age_days,
            }
        )
        if not passed:
            stale.append(item_id)

    status = VerificationStatus.BLOCKED if stale else VerificationStatus.PASSED
    return SkillOutput.ok(
        {
            "status": status,
            "staleness_checks": checks,
            "stale_sources": stale,
            "blocked_reasons": [f"{source_id} is stale or missing as_of." for source_id in stale],
            "required_inputs": ["Provide fresh price/news/filing/market data."] if stale else [],
        }
    )


def _assess_rag_confidence(payload: SkillInput) -> SkillOutput:
    query = normalize_text(payload.options.get("query"))
    contexts = coerce_mapping_list(payload.options.get("contexts") or payload.options.get("chunks") or payload.options.get("results"))
    if not contexts:
        return missing_required_output(["contexts"], skill="assess_rag_confidence")

    threshold = float(payload.options.get("threshold", 0.35))
    scores = []
    for context in contexts:
        score = context.get("score") or context.get("rerank_score")
        if score is None and query:
            score = lexical_score(query, normalize_text(context.get("text")))
        scores.append(float(score or 0))

    average = sum(scores) / len(scores) if scores else 0
    best = max(scores) if scores else 0
    coverage = sum(1 for score in scores if score >= threshold) / len(scores) if scores else 0
    confidence_score = round((average * 0.5) + (best * 0.3) + (coverage * 0.2), 6)
    if confidence_score >= threshold:
        status = VerificationStatus.PASSED
    elif confidence_score >= threshold * 0.6:
        status = VerificationStatus.NEEDS_REVISION
    else:
        status = VerificationStatus.BLOCKED

    return SkillOutput.ok(
        {
            "status": status,
            "confidence_score": confidence_score,
            "average_score": round(average, 6),
            "best_score": round(best, 6),
            "coverage": round(coverage, 6),
            "threshold": threshold,
        }
    )


def _quality_score(payload: SkillInput) -> SkillOutput:
    checks = coerce_mapping_list(payload.options.get("checks"))
    if not checks:
        for key in (
            "number_checks",
            "citation_checks",
            "language_checks",
            "staleness_checks",
            "unsupported_claim_checks",
        ):
            checks.extend(coerce_mapping_list(payload.options.get(key)))

    base_score = int(payload.options.get("base_score", 100))
    penalties = {
        VerificationStatus.NEEDS_REVISION: int(payload.options.get("needs_revision_penalty", 12)),
        VerificationStatus.NEEDS_HUMAN_REVIEW: int(payload.options.get("needs_human_review_penalty", 18)),
        VerificationStatus.BLOCKED: int(payload.options.get("blocked_penalty", 35)),
    }

    score = base_score
    status_counts: dict[str, int] = {}
    for check in checks:
        status_value = check.get("status")
        status = VerificationStatus(str(status_value)) if status_value else VerificationStatus.PASSED
        status_counts[status.value] = status_counts.get(status.value, 0) + 1
        score -= penalties.get(status, 0)

    score = max(0, min(100, score))
    if status_counts.get(VerificationStatus.BLOCKED.value):
        status = VerificationStatus.BLOCKED
    elif status_counts.get(VerificationStatus.NEEDS_HUMAN_REVIEW.value):
        status = VerificationStatus.NEEDS_HUMAN_REVIEW
    elif status_counts.get(VerificationStatus.NEEDS_REVISION.value):
        status = VerificationStatus.NEEDS_REVISION
    else:
        status = VerificationStatus.PASSED

    return SkillOutput.ok(
        {
            "status": status,
            "quality_score": score,
            "status_counts": status_counts,
            "check_count": len(checks),
        },
        effect=SkillEffect.PURE,
    )
