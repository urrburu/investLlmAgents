"""Pydantic data contracts shared across the backend.

These models mirror docs/spec/07-data-contracts.md and stay deliberately
storage-agnostic so they can be used by FastAPI, LangGraph state, and DB rows.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from invest_llm_agents.common.enums import (
    ConfidenceLevel,
    DataStatus,
    DocumentType,
    PageType,
    ReportType,
    RevisionOperation,
    RevisionReviewAction,
    RunStatus,
    TriggerType,
    VerificationStatus,
    WikiRevisionStatus,
)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SourceRef(ContractModel):
    source_id: str
    source_type: Literal["document", "chunk", "external", "calculation"]
    citation_label: str | None = None
    source_url: str | None = None
    as_of: datetime | None = None


class SourceDocument(ContractModel):
    document_id: str
    document_type: DocumentType
    title: str
    author_or_source: str | None = None
    created_at: datetime
    published_at: datetime | None = None
    raw_location: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Chunk(ContractModel):
    chunk_id: str
    document_id: str
    text: str
    page_or_offset: str | None = None
    embedding_id: str | None = None
    citation_label: str | None = None


class WikiPage(ContractModel):
    page_id: str
    namespace: str
    page_type: PageType
    title: str
    body: str
    source_refs: list[SourceRef] = Field(default_factory=list)
    confidence: ConfidenceLevel
    open_questions: list[str] = Field(default_factory=list)
    current_revision_id: str | None = None
    last_reviewed_at: datetime | None = None


class ReviewActionRecord(ContractModel):
    action: RevisionReviewAction
    reviewer: str | None = None
    requested_changes: list[str] = Field(default_factory=list)
    created_at: datetime


class WikiRevision(ContractModel):
    revision_id: str
    page_id: str
    operation: RevisionOperation
    change_summary: str
    before_refs: list[str] = Field(default_factory=list)
    after_refs: list[str] = Field(default_factory=list)
    diff_summary: str
    proposed_body: str
    source_refs: list[SourceRef] = Field(default_factory=list)
    verification_result_id: str | None = None
    status: WikiRevisionStatus = WikiRevisionStatus.DRAFT
    review_actions: list[ReviewActionRecord] = Field(default_factory=list)
    requested_changes: list[str] = Field(default_factory=list)
    created_by_agent: str
    created_at: datetime


class PortfolioHolding(ContractModel):
    ticker: str
    name: str | None = None
    quantity: Decimal
    cost_basis: Decimal | None = None
    market_price: Decimal | None = None
    market_value: Decimal | None = None
    weight: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))
    sector: str | None = None
    data_status: DataStatus


class PortfolioSnapshot(ContractModel):
    snapshot_id: str
    as_of: datetime
    base_currency: str
    holdings: list[PortfolioHolding] = Field(default_factory=list)
    cash: Decimal = Decimal("0")
    source_refs: list[SourceRef] = Field(default_factory=list)


class Claim(ContractModel):
    claim_id: str
    text: str
    source_refs: list[SourceRef] = Field(default_factory=list)


class TraceableNumber(ContractModel):
    number_id: str
    label: str
    value: Decimal
    unit: str | None = None
    formula: str
    input_refs: list[str] = Field(default_factory=list)
    generated_at: datetime


class ReportSection(ContractModel):
    section_id: str
    title: str
    status: VerificationStatus
    display_order: int
    body: str = ""
    source_refs: list[SourceRef] = Field(default_factory=list)
    hidden_reason: str | None = None


class ReportAction(ContractModel):
    action_id: str
    label: str
    action_type: Literal["upload", "select", "approve", "reject", "request_changes", "retry"]
    required_input_schema: dict[str, Any] = Field(default_factory=dict)


class ReportDraft(ContractModel):
    report_id: str
    report_type: ReportType
    title: str
    as_of: datetime | None = None
    sections: list[ReportSection] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    numbers: list[TraceableNumber] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    actions: list[ReportAction] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.PENDING


class VerificationResult(ContractModel):
    verification_result_id: str
    target_id: str
    status: VerificationStatus
    number_checks: list[dict[str, Any]] = Field(default_factory=list)
    citation_checks: list[dict[str, Any]] = Field(default_factory=list)
    language_checks: list[dict[str, Any]] = Field(default_factory=list)
    staleness_checks: list[dict[str, Any]] = Field(default_factory=list)
    required_fixes: list[str] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    safe_sections: list[str] = Field(default_factory=list)
    hidden_sections: list[str] = Field(default_factory=list)
    quality_score: int = Field(ge=0, le=100)


class AgentEvent(ContractModel):
    event_type: Literal[
        "agent_run_started",
        "external_data_fetched",
        "verification_failed",
        "report_blocked",
        "revision_proposed",
        "agent_run_completed",
    ]
    run_id: str
    created_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class RunState(ContractModel):
    run_id: str
    agent_name: str
    trigger_type: TriggerType
    started_at: datetime
    current_node: str | None = None
    last_event_at: datetime | None = None
    progress_label: str | None = None
    status: RunStatus = RunStatus.RUNNING
    input_refs: list[str] = Field(default_factory=list)
    intermediate_artifacts: list[str] = Field(default_factory=list)
    report_id: str | None = None
    revision_id: str | None = None
    verification_result_id: str | None = None
    verification_status: VerificationStatus = VerificationStatus.PENDING
    warnings: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)

