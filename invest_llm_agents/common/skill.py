"""Common Skill input/output envelopes."""

from typing import Any

from pydantic import Field

from invest_llm_agents.common.enums import ErrorCode, SkillEffect, SkillStatus
from invest_llm_agents.common.models import ContractModel, SourceRef


class SkillInput(ContractModel):
    run_id: str
    source_refs: list[SourceRef] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class SkillError(ContractModel):
    error_code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    recoverable: bool = True


class SkillOutput(ContractModel):
    status: SkillStatus
    effect: SkillEffect = SkillEffect.PURE
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    error: SkillError | None = None

    @classmethod
    def ok(
        cls,
        data: dict[str, Any] | None = None,
        *,
        effect: SkillEffect = SkillEffect.PURE,
        source_refs: list[SourceRef] | None = None,
        warnings: list[str] | None = None,
    ) -> "SkillOutput":
        return cls(
            status=SkillStatus.SUCCESS,
            effect=effect,
            data=data or {},
            source_refs=source_refs or [],
            warnings=warnings or [],
        )

    @classmethod
    def partial(
        cls,
        data: dict[str, Any] | None = None,
        *,
        effect: SkillEffect = SkillEffect.PURE,
        source_refs: list[SourceRef] | None = None,
        warnings: list[str] | None = None,
    ) -> "SkillOutput":
        return cls(
            status=SkillStatus.PARTIAL,
            effect=effect,
            data=data or {},
            source_refs=source_refs or [],
            warnings=warnings or [],
        )

    @classmethod
    def needs_human_review(
        cls,
        error_code: ErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        effect: SkillEffect = SkillEffect.PURE,
        source_refs: list[SourceRef] | None = None,
        warnings: list[str] | None = None,
    ) -> "SkillOutput":
        return cls(
            status=SkillStatus.NEEDS_HUMAN_REVIEW,
            effect=effect,
            data=data or {},
            source_refs=source_refs or [],
            warnings=warnings or [],
            error=SkillError(
                error_code=error_code,
                message=message,
                details=details or {},
                recoverable=True,
            ),
        )

    @classmethod
    def blocked(
        cls,
        error_code: ErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        effect: SkillEffect = SkillEffect.PURE,
        source_refs: list[SourceRef] | None = None,
        warnings: list[str] | None = None,
    ) -> "SkillOutput":
        return cls(
            status=SkillStatus.BLOCKED,
            effect=effect,
            data=data or {},
            source_refs=source_refs or [],
            warnings=warnings or [],
            error=SkillError(
                error_code=error_code,
                message=message,
                details=details or {},
                recoverable=False,
            ),
        )
