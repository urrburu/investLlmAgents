# 데이터 계약 스펙

이 문서는 Agent와 Skill이 공유하는 최소 데이터 구조를 정의한다. 저장소의 기준은 PostgreSQL이며, Pydantic 모델과 DB schema는 같은 필드 의미를 유지해야 한다.

## 공통 원칙

- 모든 객체는 안정적인 `id`를 가진다.
- 시간 필드는 ISO 8601 문자열로 저장한다.
- 외부 데이터에는 `source`, `source_url`, `as_of`를 남긴다.
- LLM이 생성한 문장과 코드가 계산한 숫자를 구분한다.
- 최종 출력에 쓰인 모든 주장과 숫자는 추적 가능한 `source_refs`를 가진다.

## PostgreSQL 저장소 계약

PostgreSQL을 system of record로 사용한다. Markdown 파일은 export/import 또는 사람이 읽는 출력 형식일 수 있지만, canonical 데이터는 PostgreSQL row다.

### 타입 원칙

| 데이터 성격 | PostgreSQL 타입 | 메모 |
|---|---|---|
| 내부 PK | `uuid` | DB row 식별자. 애플리케이션에서 생성해도 되고 DB default를 써도 된다. |
| 외부에 노출되는 안정 ID | `text` + `unique` | `page_id`, `revision_id`, `report_id`처럼 로그와 citation에 남는 ID. |
| 시간 | `timestamptz` | ISO 8601 문자열로 직렬화한다. |
| enum | `text` + `check` constraint | 초기 MVP에서는 migration 부담을 줄이기 위해 PostgreSQL enum type보다 check constraint를 우선한다. |
| 원문/본문 | `text` | chunk 본문, 위키 본문, revision 제안 본문. |
| 구조화된 부가 정보 | `jsonb` | `metadata`, `source_refs`, `claims`, `numbers`, 검증 check 결과. |
| 금액/수량/비율 | `numeric` | float 반올림 오차를 피한다. API 응답에서는 decimal 문자열 또는 number로 변환한다. |
| 임베딩 | `vector` 또는 외부 벡터 ID | MVP에서는 PostgreSQL `pgvector` 확장을 우선 검토한다. 확장을 쓰지 않으면 `embedding_id`는 외부 벡터 저장소 키다. |

### 테이블 매핑

| 데이터 계약 | PostgreSQL 테이블 | 주요 관계 |
|---|---|---|
| `SourceDocument` | `source_documents` | `document_id` unique |
| `Chunk` | `chunks` | `document_id`가 `source_documents.document_id`를 참조 |
| `WikiPage` | `wiki_pages` | `current_revision_id`가 승인된 `wiki_revisions.revision_id`를 참조 |
| `WikiRevision` | `wiki_revisions` | `page_id`가 `wiki_pages.page_id`를 참조 |
| `PortfolioSnapshot` | `portfolio_snapshots` | `snapshot_id` unique |
| `PortfolioHolding` | `portfolio_holdings` | `snapshot_id`가 `portfolio_snapshots.snapshot_id`를 참조 |
| `ReportDraft` | `report_drafts` | `report_id` unique |
| `VerificationResult` | `verification_results` | `target_id`는 `report_id` 또는 `revision_id`를 가리킨다. |
| `RunState` | `agent_runs` | `artifact_ids`로 report, revision, verification 결과를 연결 |

### Revision 저장 원칙

- 위키 변경은 `wiki_revisions` row로 먼저 저장한다.
- `wiki_pages.body`는 `wiki_revisions.status = accepted`가 된 뒤에만 갱신한다.
- 승인되지 않은 revision도 감사 추적을 위해 삭제하지 않는다. 폐기 시 `status = rejected`로 남긴다.
- 사람이 읽는 Markdown export를 만들더라도 export 결과는 DB의 파생물이다.

## Canonical 상태 enum

상태 이름은 아래 enum만 사용한다. 구현 중 `needs_review` 같은 축약형을 새로 만들지 않는다.

| Enum | 값 | 사용 위치 |
|---|---|---|
| `VerificationStatus` | `pending`, `passed`, `needs_revision`, `needs_human_review`, `blocked` | `ReportDraft`, `VerificationResult`, 사용자에게 보이는 검증 상태 |
| `WikiRevisionStatus` | `draft`, `verified`, `needs_human_review`, `rejected`, `accepted` | `WikiRevision` |
| `RunStatus` | `running`, `completed`, `needs_human_review`, `blocked`, `failed` | `RunState` |
| `TriggerType` | `manual`, `schedule`, `upload`, `follow_up` | `RunState.trigger_type` |
| `RevisionReviewAction` | `approve`, `reject`, `request_changes` | 사용자가 `WikiRevision`을 검토한 뒤 남기는 명시적 action |

상태 의미:

| 상태 | 의미 | 다음 동작 |
|---|---|---|
| `pending` | 아직 검증 전 | Verification Graph 실행 |
| `passed` | 숫자, 출처, 표현 검증 통과 | 최종 리포트 또는 승인 후보로 승격 |
| `needs_revision` | Agent가 수정하면 통과 가능 | 수정 요청 목록을 반영해 재생성 |
| `needs_human_review` | 사람 판단이 필요한 모호성 존재 | 확인 질문과 후보를 반환 |
| `blocked` | 안전하지 않거나 검증 불가 | 최종 출력 차단, 필요한 입력 반환 |
| `failed` | 실행 자체 실패 | 오류 로그와 복구 가능 여부 반환 |

## SourceDocument

| 필드 | 설명 |
|---|---|
| `document_id` | 원문 문서 ID |
| `document_type` | `book`, `journal`, `report`, `memo`, `news`, `filing` |
| `title` | 문서 제목 |
| `author_or_source` | 저자 또는 발행처 |
| `created_at` | 시스템 등록 시각 |
| `published_at` | 원문 발행 시각. 없으면 null |
| `raw_location` | 파일 경로, URL, 또는 저장소 키 |
| `metadata` | ticker, tag, period 등 추가 정보 |

## Chunk

| 필드 | 설명 |
|---|---|
| `chunk_id` | chunk ID |
| `document_id` | 원문 문서 ID |
| `text` | chunk 본문 |
| `page_or_offset` | 페이지, 문단, byte offset 등 위치 정보 |
| `embedding_id` | 벡터 저장소 ID |
| `citation_label` | 사용자에게 보여줄 출처 라벨 |

## WikiPage

| 필드 | 설명 |
|---|---|
| `page_id` | 위키 페이지 ID |
| `namespace` | `/wiki/books/principles` 같은 네임스페이스 |
| `page_type` | `principle`, `trade_pattern`, `asset`, `portfolio`, `rule`, `market_regime` |
| `title` | 페이지 제목 |
| `body` | 사람이 읽는 본문 |
| `source_refs` | 연결된 문서, chunk, 외부 출처 ID |
| `confidence` | `high`, `medium`, `low` |
| `open_questions` | 다음 점검 질문 |
| `current_revision_id` | 승인된 최신 revision |

## WikiRevision

| 필드 | 설명 |
|---|---|
| `revision_id` | revision ID |
| `page_id` | 대상 페이지 ID |
| `operation` | `create`, `update`, `merge`, `split` |
| `change_summary` | 변경 요약 |
| `before_refs` | 변경 전 기준이 된 page/revision/source ID 목록 |
| `after_refs` | 변경 후 연결될 page/revision/source ID 목록 |
| `diff_summary` | 사용자에게 보여줄 before/after 변경 요약 |
| `proposed_body` | 제안 본문 |
| `source_refs` | 변경 근거 |
| `verification_result_id` | 검증 결과 ID |
| `status` | `draft`, `verified`, `needs_human_review`, `rejected`, `accepted` |
| `review_actions` | 사용자가 남긴 `approve`, `reject`, `request_changes` action 이력 |
| `requested_changes` | 사용자가 수정을 요청한 경우의 구체적 요청 목록 |
| `created_by_agent` | 생성 Agent |
| `created_at` | 생성 시각 |

## PortfolioSnapshot

| 필드 | 설명 |
|---|---|
| `snapshot_id` | 포트폴리오 스냅샷 ID |
| `as_of` | 기준 시각 |
| `base_currency` | 기준 통화 |
| `holdings` | `PortfolioHolding` 목록 |
| `cash` | 현금 잔고 |
| `source_refs` | 계좌 파일, 수동 입력, API 응답 등 |

## PortfolioHolding

| 필드 | 설명 |
|---|---|
| `ticker` | 정규화된 ticker |
| `name` | 종목명 |
| `quantity` | 보유 수량 |
| `cost_basis` | 평균 단가. 없으면 null |
| `market_price` | 현재가. 없으면 null |
| `market_value` | 평가금액 |
| `weight` | 포트폴리오 비중 |
| `sector` | 섹터 |
| `data_status` | `complete`, `partial`, `missing_price`, `missing_cost` |

## ReportDraft

| 필드 | 설명 |
|---|---|
| `report_id` | 리포트 ID |
| `report_type` | `daily_check`, `weekly_review`, `stock_snapshot`, `portfolio_report`, `market_brief` |
| `sections` | 구조화된 섹션 목록. 각 섹션은 `section_id`, `title`, `status`, `display_order`, `source_refs`, `hidden_reason`을 가진다. |
| `claims` | 검증 대상 주장 목록 |
| `numbers` | 검증 대상 숫자 목록 |
| `source_refs` | 전체 출처 목록 |
| `actions` | 사용자에게 보여줄 다음 행동 목록. `action_id`, `label`, `action_type`, `required_input_schema`를 가진다. |
| `verification_status` | `pending`, `passed`, `needs_revision`, `needs_human_review`, `blocked` |

## VerificationResult

| 필드 | 설명 |
|---|---|
| `verification_result_id` | 검증 결과 ID |
| `target_id` | ReportDraft 또는 WikiRevision ID |
| `status` | `passed`, `needs_revision`, `needs_human_review`, `blocked` |
| `number_checks` | 숫자 검증 결과 |
| `citation_checks` | 출처 검증 결과 |
| `language_checks` | 금지 표현 검사 결과 |
| `staleness_checks` | 데이터 최신성 검사 결과 |
| `required_fixes` | 수정이 필요한 항목 |
| `required_inputs` | 사람이 제공해야 하는 입력 또는 선택지 |
| `safe_sections` | 부분 실패 시 사용자에게 보여도 되는 section ID 목록 |
| `hidden_sections` | 검증 실패 때문에 숨긴 section ID 목록 |
| `quality_score` | 0~100 점수 |

## RunState

| 필드 | 설명 |
|---|---|
| `run_id` | Agent 실행 ID |
| `agent_name` | 실행 Agent |
| `trigger_type` | `manual`, `schedule`, `upload`, `follow_up` |
| `started_at` | 시작 시각 |
| `current_node` | 현재 실행 중이거나 마지막으로 완료된 Graph node |
| `last_event_at` | 마지막 관측 이벤트 시각 |
| `progress_label` | 사용자에게 보여줄 짧은 진행 상태 문구 |
| `status` | `running`, `completed`, `needs_human_review`, `blocked`, `failed` |
| `warnings` | 계속 진행 가능한 경고 |
| `blocked_reasons` | 최종 출력을 막은 이유 |
| `artifact_ids` | 생성한 report, revision, verification ID |

## Pydantic 모델 초안

구현은 아래 형태에서 시작한다. 이 Pydantic 모델은 PostgreSQL row를 API/Graph state로 주고받기 위한 직렬화 계약이다.

```python
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class VerificationStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    NEEDS_REVISION = "needs_revision"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    BLOCKED = "blocked"


class DataStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING_PRICE = "missing_price"
    MISSING_COST = "missing_cost"


class RevisionReviewAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"


class SourceRef(BaseModel):
    source_id: str
    source_type: Literal["document", "chunk", "external", "calculation"]
    citation_label: str | None = None


class ReportSection(BaseModel):
    section_id: str
    title: str
    status: VerificationStatus
    display_order: int
    source_refs: list[SourceRef] = Field(default_factory=list)
    hidden_reason: str | None = None


class ReportAction(BaseModel):
    action_id: str
    label: str
    action_type: Literal["upload", "select", "approve", "reject", "request_changes", "retry"]
    required_input_schema: dict[str, Any] = Field(default_factory=dict)


class PortfolioHolding(BaseModel):
    ticker: str
    name: str | None = None
    quantity: float
    cost_basis: float | None = None
    market_price: float | None = None
    market_value: float | None = None
    weight: float | None = Field(default=None, ge=0, le=1)
    sector: str | None = None
    data_status: DataStatus


class VerificationResult(BaseModel):
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
```

## 최소 JSON 예시

### PortfolioSnapshot

```json
{
  "snapshot_id": "portfolio_2026-06-28",
  "as_of": "2026-06-28T09:00:00+09:00",
  "base_currency": "USD",
  "holdings": [
    {
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "quantity": 10,
      "cost_basis": 180.5,
      "market_price": 195.2,
      "market_value": 1952.0,
      "weight": 0.34,
      "sector": "Technology",
      "data_status": "complete"
    }
  ],
  "cash": 1200.0,
  "source_refs": ["source_manual_portfolio_csv"]
}
```

### VerificationResult

```json
{
  "verification_result_id": "verify_report_001",
  "target_id": "report_daily_001",
  "status": "needs_human_review",
  "number_checks": [
    {
      "field": "holdings[0].weight",
      "status": "passed",
      "calculation": "market_value / total_portfolio_value"
    }
  ],
  "citation_checks": [
    {
      "claim_id": "claim_003",
      "status": "missing",
      "error_code": "MISSING_CITATION"
    }
  ],
  "language_checks": [],
  "staleness_checks": [],
  "required_fixes": ["claim_003에 source_refs를 추가하거나 주장을 제거한다."],
  "required_inputs": ["claim_003의 원문 출처를 제공하거나 해당 주장을 제거한다."],
  "safe_sections": ["portfolio_weights"],
  "hidden_sections": ["unsupported_claims"],
  "quality_score": 72
}
```

## 수용 기준

- 데이터 계약 없이 Agent나 Skill을 추가하지 않는다.
- `ReportDraft.verification_status`가 `passed`가 아니면 최종 응답으로 승격하지 않는다.
- `WikiRevision.status`가 `accepted`가 되기 전까지 기존 위키 본문을 덮어쓰지 않는다.
- 외부 데이터가 오래되었거나 누락되면 `data_status`와 `blocked_reasons`에 남긴다.
- 상태 enum은 이 문서의 Canonical 상태 enum과 일치해야 한다.
