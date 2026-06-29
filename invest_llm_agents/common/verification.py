"""Verification gate helpers and rescue payloads."""

from typing import Any

from pydantic import Field

from invest_llm_agents.common.enums import ErrorCode, VerificationStatus
from invest_llm_agents.common.models import ContractModel, ReportDraft, VerificationResult


FORBIDDEN_LANGUAGE_RULES: tuple[tuple[ErrorCode, tuple[str, ...]], ...] = (
    (
        ErrorCode.UNSUPPORTED_RECOMMENDATION,
        (
            "지금 매수",
            "지금 매도",
            "매수해야",
            "매도해야",
            "반드시 오른다",
            "수익이 보장",
            "목표가는",
            "buy now",
            "sell now",
            "guaranteed return",
            "price target is",
        ),
    ),
)


class RescuePayload(ContractModel):
    verification_status: VerificationStatus
    error_code: ErrorCode
    message: str
    blocked_reasons: list[str] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    safe_sections: list[str] = Field(default_factory=list)
    hidden_sections: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    questions: list[dict[str, Any]] = Field(default_factory=list)


def check_recommendation_language(text: str) -> list[dict[str, Any]]:
    """Detect direct recommendation phrases banned by the output spec."""
    normalized = text.casefold()
    checks: list[dict[str, Any]] = []

    for error_code, phrases in FORBIDDEN_LANGUAGE_RULES:
        for phrase in phrases:
            if phrase.casefold() in normalized:
                checks.append(
                    {
                        "status": VerificationStatus.BLOCKED,
                        "error_code": error_code,
                        "matched_phrase": phrase,
                        "message": "투자 지시나 보장처럼 보이는 표현입니다.",
                    }
                )

    return checks


def build_rescue_payload(
    *,
    error_code: ErrorCode,
    message: str,
    status: VerificationStatus = VerificationStatus.BLOCKED,
    blocked_reasons: list[str] | None = None,
    required_inputs: list[str] | None = None,
    safe_sections: list[str] | None = None,
    hidden_sections: list[str] | None = None,
    warnings: list[str] | None = None,
    questions: list[dict[str, Any]] | None = None,
) -> RescuePayload:
    return RescuePayload(
        verification_status=status,
        error_code=error_code,
        message=message,
        blocked_reasons=blocked_reasons or [],
        required_inputs=required_inputs or [],
        safe_sections=safe_sections or [],
        hidden_sections=hidden_sections or [],
        warnings=warnings or [],
        questions=questions or [],
    )


def report_can_be_promoted(
    report: ReportDraft,
    verification_result: VerificationResult,
) -> bool:
    return (
        report.report_id == verification_result.target_id
        and report.verification_status == VerificationStatus.PASSED
        and verification_result.status == VerificationStatus.PASSED
    )


def rescue_from_verification_result(
    verification_result: VerificationResult,
    *,
    error_code: ErrorCode,
    message: str,
) -> RescuePayload:
    return build_rescue_payload(
        error_code=error_code,
        message=message,
        status=verification_result.status,
        blocked_reasons=verification_result.required_fixes,
        required_inputs=verification_result.required_inputs,
        safe_sections=verification_result.safe_sections,
        hidden_sections=verification_result.hidden_sections,
    )

