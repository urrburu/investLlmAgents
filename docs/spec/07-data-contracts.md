# 데이터 계약 스펙

이 문서는 Agent와 Skill이 공유하는 최소 데이터 구조를 정의한다. 구현 언어와 저장소는 바뀔 수 있지만, 필드 의미는 유지한다.

## 공통 원칙

- 모든 객체는 안정적인 `id`를 가진다.
- 시간 필드는 ISO 8601 문자열로 저장한다.
- 외부 데이터에는 `source`, `source_url`, `as_of`를 남긴다.
- LLM이 생성한 문장과 코드가 계산한 숫자를 구분한다.
- 최종 출력에 쓰인 모든 주장과 숫자는 추적 가능한 `source_refs`를 가진다.

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
| `proposed_body` | 제안 본문 |
| `source_refs` | 변경 근거 |
| `verification_result_id` | 검증 결과 ID |
| `status` | `draft`, `verified`, `needs_human_review`, `rejected`, `accepted` |
| `created_by_agent` | 생성 Agent |

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
| `sections` | 구조화된 섹션 목록 |
| `claims` | 검증 대상 주장 목록 |
| `numbers` | 검증 대상 숫자 목록 |
| `source_refs` | 전체 출처 목록 |
| `verification_status` | `pending`, `passed`, `needs_revision`, `blocked` |

## VerificationResult

| 필드 | 설명 |
|---|---|
| `verification_result_id` | 검증 결과 ID |
| `target_id` | ReportDraft 또는 WikiRevision ID |
| `status` | `passed`, `needs_revision`, `blocked` |
| `number_checks` | 숫자 검증 결과 |
| `citation_checks` | 출처 검증 결과 |
| `language_checks` | 금지 표현 검사 결과 |
| `staleness_checks` | 데이터 최신성 검사 결과 |
| `required_fixes` | 수정이 필요한 항목 |
| `quality_score` | 0~100 점수 |

## RunState

| 필드 | 설명 |
|---|---|
| `run_id` | Agent 실행 ID |
| `agent_name` | 실행 Agent |
| `trigger_type` | `manual`, `schedule`, `upload`, `follow_up` |
| `started_at` | 시작 시각 |
| `status` | `running`, `completed`, `needs_review`, `blocked`, `failed` |
| `warnings` | 계속 진행 가능한 경고 |
| `blocked_reasons` | 최종 출력을 막은 이유 |
| `artifact_ids` | 생성한 report, revision, verification ID |

## 수용 기준

- 데이터 계약 없이 Agent나 Skill을 추가하지 않는다.
- `ReportDraft.verification_status`가 `passed`가 아니면 최종 응답으로 승격하지 않는다.
- `WikiRevision.status`가 `accepted`가 되기 전까지 기존 위키 본문을 덮어쓰지 않는다.
- 외부 데이터가 오래되었거나 누락되면 `data_status`와 `blocked_reasons`에 남긴다.
