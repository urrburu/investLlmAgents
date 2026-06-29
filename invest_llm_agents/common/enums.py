"""Canonical enum values from the spec documents."""

from enum import StrEnum


class VerificationStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    NEEDS_REVISION = "needs_revision"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    BLOCKED = "blocked"


class WikiRevisionStatus(StrEnum):
    DRAFT = "draft"
    VERIFIED = "verified"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    REJECTED = "rejected"
    ACCEPTED = "accepted"


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    BLOCKED = "blocked"
    FAILED = "failed"


class TriggerType(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    UPLOAD = "upload"
    FOLLOW_UP = "follow_up"


class RevisionReviewAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"


class DataStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING_PRICE = "missing_price"
    MISSING_COST = "missing_cost"


class PageType(StrEnum):
    PRINCIPLE = "principle"
    TRADE_PATTERN = "trade_pattern"
    ASSET = "asset"
    PORTFOLIO = "portfolio"
    RULE = "rule"
    MARKET_REGIME = "market_regime"


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DocumentType(StrEnum):
    BOOK = "book"
    JOURNAL = "journal"
    REPORT = "report"
    MEMO = "memo"
    NEWS = "news"
    FILING = "filing"


class ReportType(StrEnum):
    DAILY_CHECK = "daily_check"
    WEEKLY_REVIEW = "weekly_review"
    STOCK_SNAPSHOT = "stock_snapshot"
    PORTFOLIO_REPORT = "portfolio_report"
    MARKET_BRIEF = "market_brief"


class RevisionOperation(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    MERGE = "merge"
    SPLIT = "split"


class SkillStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    BLOCKED = "blocked"
    FAILED = "failed"


class SkillEffect(StrEnum):
    PURE = "pure"
    READ_EXTERNAL = "read_external"
    PROPOSE_REVISION = "propose_revision"
    WRITE_INTERNAL = "write_internal"


class ErrorCode(StrEnum):
    SOURCE_PARSE_FAILED = "SOURCE_PARSE_FAILED"
    MISSING_CITATION = "MISSING_CITATION"
    NUMBER_MISMATCH = "NUMBER_MISMATCH"
    STALE_MARKET_DATA = "STALE_MARKET_DATA"
    AMBIGUOUS_TICKER = "AMBIGUOUS_TICKER"
    UNSUPPORTED_RECOMMENDATION = "UNSUPPORTED_RECOMMENDATION"
    LOW_RAG_CONFIDENCE = "LOW_RAG_CONFIDENCE"
    PARTIAL_EXTERNAL_OUTAGE = "PARTIAL_EXTERNAL_OUTAGE"

