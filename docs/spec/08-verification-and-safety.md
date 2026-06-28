# 검증 및 안전 스펙

이 시스템의 안전 기준은 단순하다. **근거가 없거나 검증되지 않은 내용은 부드럽게 포장하지 않고, 보류 또는 확인 요청으로 보여준다.**

## 출력 상태

| 상태 | 의미 | 사용자에게 보이는 형태 |
|---|---|---|
| `passed` | 숫자, 출처, 표현 검사를 통과 | 최종 리포트 |
| `needs_revision` | 수정하면 통과 가능 | 수정 요청과 실패 항목 |
| `needs_human_review` | 해석 또는 출처 판단에 사람 확인 필요 | 확인 질문 목록 |
| `blocked` | 안전하지 않거나 검증 불가 | 차단 사유와 필요한 입력 |

## 필수 검증 게이트

| 게이트 | 검사 내용 | 실패 시 |
|---|---|---|
| 숫자 검증 | 수익률, 비중, 평가금액, 지표 계산이 원천 데이터와 일치하는지 | 해당 숫자를 출력하지 않거나 계산 보류 |
| Citation 검증 | 주요 주장마다 출처가 있는지 | 주장 제거 또는 확인 요청 |
| 최신성 검증 | 가격, 뉴스, 공시, 시장 지표의 `as_of`가 허용 범위인지 | 최신 데이터 요청 또는 판단 보류 |
| 금지 표현 검사 | 매수/매도 지시, 목표가, 보장 표현이 없는지 | 표현 수정 또는 출력 차단 |
| RAG 충분성 검사 | 검색 근거가 질문에 충분히 관련 있는지 | 낮은 신뢰도 표시 또는 사람 검토 |

## 금지 표현 예시

| 금지 | 허용 대체 |
|---|---|
| "지금 매수해야 한다" | "매수 여부를 판단하기 전에 확인할 항목은..." |
| "목표가는 120달러다" | "현재 thesis에서 추적할 가격 관련 변수는..." |
| "수익이 보장된다" | "이 시나리오가 맞으려면 필요한 전제는..." |
| "이 종목은 반드시 오른다" | "상승 시나리오와 반대 시나리오를 나누면..." |
| "자동으로 비중을 줄인다" | "비중 축소 검토가 필요한 신호는..." |

## Error & Rescue Registry

| 오류 코드 | 트리거 | Rescue |
|---|---|---|
| `SOURCE_PARSE_FAILED` | 원문 파싱 실패 | 해당 문서 제외, 실패 문서 목록 반환 |
| `MISSING_CITATION` | 주요 주장에 출처 없음 | 주장 제거 또는 `needs_human_review` |
| `NUMBER_MISMATCH` | 계산 결과와 원천 데이터 불일치 | 숫자 출력 차단, 계산 로그 반환 |
| `STALE_MARKET_DATA` | 기준일이 오래된 시장 데이터 | 국면 판단 보류, 최신 데이터 요청 |
| `AMBIGUOUS_TICKER` | ticker 후보가 여러 개 | 후보 목록 반환, 분석 보류 |
| `UNSUPPORTED_RECOMMENDATION` | 추천처럼 보이는 표현 생성 | 문장 수정 또는 출력 차단 |
| `LOW_RAG_CONFIDENCE` | 검색 근거 부족 | 낮은 신뢰도 표시, 추가 자료 요청 |
| `PARTIAL_EXTERNAL_OUTAGE` | 외부 API 일부 실패 | 가능한 섹션만 생성하고 누락 표시 |

## Failure Modes Registry

| 실패 모드 | 사용자 영향 | 방지책 |
|---|---|---|
| 검증 실패를 숨긴 자연스러운 답변 | 사용자가 잘못된 확신을 얻음 | `verification_status`를 출력 승격 조건으로 사용 |
| 오래된 가격으로 현재 판단 | 리포트가 현재 상태를 왜곡 | 모든 시장 데이터에 `as_of` 표시 |
| RAG가 관련 없는 chunk를 근거로 사용 | 출처는 있으나 주장이 틀림 | rerank와 RAG 충분성 검사 추가 |
| Agent가 위키를 직접 덮어씀 | 잘못된 지식이 장기 저장됨 | revision 승인 모델 사용 |
| 시황을 이분법으로 단정 | 혼합 국면을 놓침 | `mixed`, `insufficient_data` 상태 허용 |
| Persona Formatter가 안전 문구를 제거 | 최종 답변에서 위험이 가려짐 | Formatter 이후에도 금지 표현 재검사 |

## 관측 이벤트

각 실행은 아래 이벤트를 남긴다.

| 이벤트 | 필수 필드 |
|---|---|
| `agent_run_started` | `run_id`, `agent_name`, `trigger_type` |
| `external_data_fetched` | `run_id`, `source`, `as_of`, `status` |
| `verification_failed` | `run_id`, `target_id`, `error_code`, `required_fixes` |
| `report_blocked` | `run_id`, `blocked_reasons` |
| `revision_proposed` | `run_id`, `page_id`, `revision_id`, `status` |
| `agent_run_completed` | `run_id`, `status`, `artifact_ids` |

## 수용 기준

- 검증 실패는 사용자에게 숨기지 않는다.
- 부분 실패는 부분 성공과 명확히 분리해 표시한다.
- 금지 표현 검사는 Formatter 전후로 모두 수행한다.
- 최종 리포트에는 기준일, 출처, 확인 필요 항목이 포함된다.
- 위키 저장은 revision 승인 이후에만 일어난다.
