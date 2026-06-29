# 제품 디자인 스펙

이 문서는 사용자가 실제로 보게 되는 정보 구조, 리포트 템플릿, 승인 흐름, 실패 상태 표현을 정의한다. 현재 구현은 FastAPI/LangGraph 백엔드 중심이므로 MVP 1의 1차 사용자 표면은 웹 대시보드가 아니라 **Markdown 리포트, CLI/API 응답, DB-backed revision review**다.

## 디자인 리뷰 요약

| 패스 | 초기 평가 | 보강 후 목표 | 반영 내용 |
|---|---:|---:|---|
| 정보 구조 | 4/10 | 8/10 | 주요 사용자 표면, 우선순위, ASCII 구조도 추가 |
| 상태 커버리지 | 3/10 | 9/10 | loading, empty, error, success, partial 상태 표 추가 |
| 사용자 여정 | 4/10 | 8/10 | 5초, 5분, 장기 신뢰 기준과 스토리보드 추가 |
| AI slop 위험 | 5/10 | 9/10 | 투자 추천처럼 보이는 색/문구/카드 패턴 금지 |
| 디자인 시스템 | 2/10 | 8/10 | 색, 타이포그래피, 밀도, 컴포넌트 원칙 정의 |
| 반응형/접근성 | 2/10 | 8/10 | 모바일, 키보드, 스크린리더, 대비 기준 정의 |
| 미해결 결정 | 4/10 | 8/10 | MVP 1 출력 위치와 승인 UX를 확정 |

## 제품 디자인 원칙

1. **점검이 추천보다 먼저 보인다.** 사용자는 "무엇을 사라"가 아니라 "무엇을 확인해야 하는가"를 먼저 본다.
2. **검증 상태는 장식이 아니라 구조다.** `passed`, `needs_revision`, `needs_human_review`, `blocked`는 모든 리포트와 revision의 첫 화면에 표시한다.
3. **출처는 접힌 부록이 아니다.** 주요 주장 옆에는 최소한 source label 또는 `source_refs` 요약이 붙는다.
4. **숫자와 문장을 분리한다.** 계산된 숫자, LLM 해석, 사용자 확인 질문을 시각적으로 섞지 않는다.
5. **부분 실패는 부분 성공과 분리한다.** 가능한 섹션과 숨긴 섹션을 같은 문단에 섞지 않는다.
6. **색은 투자 방향이 아니라 시스템 상태를 뜻한다.** 초록은 "매수", 빨강은 "매도"를 암시하지 않는다.
7. **승인은 명시적 행동이다.** 위키 revision은 diff, 근거, 검증 결과를 본 뒤 `approve`, `reject`, `request_changes` 중 하나로 처리한다.

## NOT In Scope

| 항목 | 이유 |
|---|---|
| 실시간 매매 버튼 | 제품 경계가 투자 점검에서 자동 의사결정으로 넘어간다. |
| 목표가 중심 종목 화면 | 출력 제약의 금지 항목과 충돌한다. |
| 추천 랭킹 대시보드 | 사용자에게 투자 지시처럼 읽힐 위험이 높다. |
| MVP 1 웹 대시보드 | 현재 구현 우선순위는 데이터 계약, Graph, 검증 게이트다. |
| 화려한 마케팅 랜딩 | 이 제품의 1차 경험은 반복 점검 도구다. |

## What Already Exists

| 기존 문서 | 재사용할 디자인 계약 |
|---|---|
| [00-overview.md](00-overview.md) | 투자 추천 엔진이 아니라 감사 가능한 작업대라는 제품 경계 |
| [01-llmwiki-structure.md](01-llmwiki-structure.md) | 위키 네임스페이스와 revision 승인 모델 |
| [04-langgraph-graphs.md](04-langgraph-graphs.md) | 검증 Graph를 우회하지 않는 실행 구조 |
| [06-output-constraints.md](06-output-constraints.md) | 허용/금지 출력과 MVP 경계 |
| [07-data-contracts.md](07-data-contracts.md) | `ReportDraft`, `WikiRevision`, `VerificationResult`, `RunState` 계약 |
| [08-verification-and-safety.md](08-verification-and-safety.md) | rescue payload, 오류 코드, 사용자에게 보이는 상태 |

## MVP 사용자 표면

MVP 1은 웹 화면을 만들기 전에 아래 네 가지 표면을 먼저 완성한다.

| 표면 | 사용자 목표 | 1차 출력 | 성공 기준 |
|---|---|---|---|
| 포트폴리오 점검 리포트 | 현재 보유 상태와 원칙 충돌을 빠르게 본다. | Markdown/API JSON | 주요 숫자, 출처, 확인 질문이 검증 상태와 함께 보인다. |
| 위키 revision 검토 | Agent가 제안한 지식 변경을 승인하거나 보류한다. | Markdown diff + API action | 변경 요약, before/after, 근거, 검증 결과를 보고 명시적으로 처리한다. |
| 검증 실패 rescue | 왜 최종 리포트가 막혔는지 이해한다. | Markdown/API JSON | 차단 사유, 필요한 입력, 가능한 안전 섹션이 분리되어 보인다. |
| 실행 상태 조회 | 긴 Agent 실행이 어디까지 왔는지 확인한다. | CLI/API JSON | `running`, `needs_human_review`, `blocked`, `completed`가 artifact와 연결된다. |

### 정보 구조

```
Home / CLI command
  -> Run detail
      -> Status strip
      -> Generated artifact list
      -> Required user actions
      -> Event log summary

Portfolio report
  -> Verification status
  -> Top 3 check items
  -> Portfolio exposure
  -> Principle conflicts
  -> Source and calculation log
  -> Next review questions

Wiki revision review
  -> Change summary
  -> Before / after diff
  -> Evidence and source refs
  -> Verification result
  -> Approve / reject / request changes

Rescue response
  -> What stopped the output
  -> What is still safe to show
  -> What was hidden
  -> Required input
```

## Screen And Document Hierarchy

### 1. Portfolio Check Report

첫 5초 안에 사용자가 읽어야 하는 순서는 아래와 같다.

1. 검증 상태와 기준일
2. 지금 확인해야 할 상위 3개 항목
3. 포트폴리오 비중, 집중도, 현금 비중
4. 내 원칙과 충돌 가능성이 있는 항목
5. 출처와 계산 로그

Markdown 템플릿:

```markdown
# 포트폴리오 점검 리포트

검증 상태: passed
기준일: 2026-06-28T09:00:00+09:00
출처: source_manual_portfolio_csv, price_api_2026_06_28

## 먼저 볼 3가지

1. [확인 필요] 기술 섹터 비중이 55%입니다. 내 집중도 규칙과 비교가 필요합니다.
2. [주의] AAPL 가격 데이터는 최신이나 공시 요약은 누락되었습니다.
3. [점검] 최근 손실 패턴과 유사한 진입 조건이 있는지 확인합니다.

## 포트폴리오 상태

| 항목 | 값 | 근거 |
|---|---:|---|
| 총 평가금액 | 3,152.00 USD | calculation:portfolio_total |
| 현금 비중 | 38.1% | source_manual_portfolio_csv |
| 최대 단일 종목 비중 | 34.0% | calculation:holding_weight |

## 원칙 충돌 가능성

| 원칙 | 현재 상태 | 판단 |
|---|---|---|
| 단일 종목 30% 초과 시 재점검 | AAPL 34.0% | 확인 필요 |

## 다음 질문

- AAPL 비중 30% 초과를 예외로 둘 근거가 있습니까?
- 공시 API 누락 상태에서 뉴스 기반 판단을 보류할까요?
```

### 2. Wiki Revision Review

Revision 검토는 "문서 생성 결과"가 아니라 "장기 기억을 바꾸는 승인 행동"이다. 화면 또는 Markdown은 diff보다 먼저 변경 의도와 검증 상태를 보여준다.

```markdown
# 위키 Revision 검토

revision_id: rev_2026_06_28_001
page_id: wiki_rules_concentration
operation: update
status: verified

## 변경 요약

단일 종목 집중도 규칙에 "30% 초과 시 다음 점검에서 재검토" 조건을 추가합니다.

## Before / After

| Before | After |
|---|---|
| 단일 종목 집중도는 주기적으로 확인한다. | 단일 종목 비중이 30%를 초과하면 다음 점검에서 예외 근거를 기록한다. |

## 근거

- source_book_001_chunk_032
- journal_2026_05_loss_review

## 검증 결과

| 게이트 | 상태 | 메모 |
|---|---|---|
| citation | passed | 모든 주장에 source_refs 있음 |
| unsupported_claims | passed | 추천 표현 없음 |

## 가능한 행동

- approve: 현재 위키에 반영
- reject: 폐기하고 사유 기록
- request_changes: 수정 요청을 남기고 재생성
```

### 3. Verification Rescue

Rescue는 사과문이 아니라 다음 행동을 알려주는 인터페이스다. 사용자는 "왜 막혔는가", "무엇은 볼 수 있는가", "무엇을 주면 풀리는가"를 바로 알아야 한다.

```markdown
# 검토가 필요한 결과입니다

상태: blocked
오류 코드: NUMBER_MISMATCH

## 막힌 이유

포트폴리오 비중 계산 결과가 원천 데이터와 일치하지 않습니다.

## 안전하게 보여줄 수 있는 섹션

없음

## 숨긴 섹션

- portfolio_weights
- return_summary

## 필요한 입력

- 최신 포트폴리오 CSV를 다시 업로드한다.
- 또는 market_value 계산 로그를 확인한다.
```

### 4. Stock Snapshot

종목 Snapshot은 점수판이 아니다. "최근 변화가 기존 thesis와 리스크에 어떤 질문을 만든다"가 중심이다.

우선순위:

1. 검증 상태, ticker, 기준일
2. thesis에 영향을 줄 수 있는 변화
3. 관련 위키 원칙과 리스크
4. 출처별 요약
5. 확인 질문

금지:

- "매수", "매도", "목표가"를 CTA처럼 보이게 하지 않는다.
- 상승/하락 색을 초록/빨강으로 자동 매핑하지 않는다.
- 뉴스 헤드라인만으로 thesis 변경을 단정하지 않는다.

## Interaction State Coverage

| 기능 | Loading | Empty | Error | Success | Partial |
|---|---|---|---|---|---|
| 원문 업로드 | 파일명, 크기, 파싱 단계 표시 | 업로드된 원문 없음. 첫 원문 추가 action 제공 | `SOURCE_PARSE_FAILED`와 실패 파일명 표시 | 생성된 `document_id`, chunk 수, 다음 단계 표시 | 일부 문서 실패, 성공 문서와 실패 문서 분리 |
| 포트폴리오 점검 | 가격 조회, 계산, 검증 단계 표시 | 포트폴리오 없음. CSV 샘플 링크 또는 스키마 제공 | 입력 필드 오류와 수정 위치 표시 | 검증 통과 리포트 표시 | 누락 종목, stale 가격, 숨긴 섹션 분리 |
| 위키 revision | 검증 중인 게이트 표시 | 검토할 revision 없음 | citation 부족 또는 충돌 사유 표시 | approve/reject/request_changes 가능 | 일부 게이트 통과, 사람 확인 질문 표시 |
| 시황 브리프 | 지수, 금리, VIX, 섹터 조회 단계 표시 | 시장 데이터 없음. 데이터 공급원 설정 action 제공 | stale data 또는 API 실패 표시 | risk_on/risk_off/mixed와 근거 표시 | 포트폴리오 연결 누락, 시황만 표시 |
| 종목 Snapshot | ticker 정규화, 데이터 조회 단계 표시 | 분석 이력 없음. ticker 입력 action 제공 | `AMBIGUOUS_TICKER` 후보 목록 표시 | 변화 요약과 확인 질문 표시 | 공시 누락, 뉴스 기반 주장 제한 표시 |
| 실행 상태 | node별 진행 상태 표시 | 실행 없음. 새 실행 action 제공 | failed와 retry 가능 여부 표시 | artifact_ids와 완료 상태 표시 | warning, missing_inputs, blocked_reasons 표시 |

## User Journey

| 단계 | 사용자 행동 | 감정 | 디자인 지원 |
|---|---|---|---|
| 1 | 포트폴리오 CSV 또는 원문을 넣는다. | "이게 제대로 읽힐까?" | 입력 스키마와 파싱 상태를 즉시 보여준다. |
| 2 | 점검 실행을 기다린다. | "어디서 멈춘 거지?" | Graph node 진행 상태와 마지막 이벤트를 보여준다. |
| 3 | 리포트 첫 화면을 본다. | "그래서 지금 확인할 것은?" | 상위 3개 확인 항목을 먼저 보여준다. |
| 4 | 원칙 충돌과 출처를 확인한다. | "이 판단을 믿어도 되나?" | 숫자, 해석, 출처를 분리해 보여준다. |
| 5 | 위키 revision을 승인한다. | "내 장기 기억을 바꿔도 되나?" | before/after diff, 근거, 검증 결과를 한 곳에 둔다. |
| 6 | 실패 상태를 만난다. | "뭘 고쳐야 하지?" | 숨긴 섹션과 필요한 입력을 분리해 안내한다. |

시간 축 기준:

- 5초: 상태, 기준일, 상위 확인 항목이 보여야 한다.
- 5분: 사용자는 원칙 충돌과 출처를 따라가며 판단 이유를 이해해야 한다.
- 장기: 위키 revision 이력과 검증 로그가 쌓여 시스템을 감사할 수 있어야 한다.

## Design System

### 분류

이 제품은 마케팅 랜딩이 아니라 **APP UI**다. 화면이 생길 경우 조용하고 밀도 높은 작업대처럼 보여야 한다.

### 색 토큰

| 토큰 | 값 | 용도 |
|---|---|---|
| `--surface` | `#F8FAFC` | 페이지 배경 |
| `--panel` | `#FFFFFF` | 주요 작업 영역 |
| `--ink` | `#172033` | 본문 |
| `--muted` | `#64748B` | 보조 설명 |
| `--line` | `#CBD5E1` | 구분선 |
| `--brand` | `#1D4ED8` | 주요 action, 링크 |
| `--ok` | `#15803D` | 검증 통과 |
| `--review` | `#B45309` | 사람 확인 필요 |
| `--danger` | `#B91C1C` | 차단, 안전 실패 |
| `--info` | `#0F766E` | 출처, 계산 로그 |

색 사용 규칙:

- `--ok`는 "매수"가 아니라 "검증 통과"만 뜻한다.
- `--danger`는 "매도"가 아니라 "차단 또는 실패"만 뜻한다.
- 투자 방향성에는 색 대신 `상승 시나리오`, `반대 시나리오`, `확인 필요` 라벨을 쓴다.

### Typography

- 한국어 UI 기본 글꼴은 `Pretendard`를 우선한다.
- 폴백은 `"Noto Sans KR", "Apple SD Gothic Neo", sans-serif`다.
- 숫자 표와 로그에는 `JetBrains Mono` 또는 `SFMono-Regular`를 쓴다.
- 본문 최소 크기는 16px이다.
- 대시보드 내부 제목은 18-22px 범위로 제한한다.

### Layout

- 카드 남용을 피하고, 반복 항목이나 action panel에만 card를 쓴다.
- 주요 작업 화면은 `상태 strip -> 핵심 요약 -> 상세 표 -> 출처/로그` 순서다.
- 표는 zebra stripe보다 명확한 column alignment를 우선한다.
- border radius는 8px 이하를 기본으로 한다.
- 장식용 gradient, 원형 icon badge, 3-column feature grid를 쓰지 않는다.

### Components

| 컴포넌트 | 사용 위치 | 필수 상태 |
|---|---|---|
| Status strip | 모든 리포트와 revision 상단 | passed, needs_revision, needs_human_review, blocked |
| Source chip | 주장, 숫자, 문단 옆 | source_id, as_of, confidence |
| Calculation row | 숫자 표 | formula, input refs, generated_at |
| Diff block | revision review | before, after, changed fields |
| Action bar | revision review | approve, reject, request_changes |
| Rescue panel | 실패 응답 | blocked_reasons, safe_sections, hidden_sections, required_inputs |
| Event log summary | run detail | last event, warnings, artifact_ids |

## Responsive And Accessibility

### Desktop

- 왼쪽에는 실행/문서 목록, 오른쪽에는 선택된 report 또는 revision detail을 둔다.
- 핵심 action bar는 detail 상단과 하단에 모두 둔다.
- 큰 표는 column 숨김보다 horizontal scroll과 summary row를 우선한다.

### Mobile

- 첫 화면에는 status strip, 기준일, 상위 3개 확인 항목만 둔다.
- 상세 표, 출처, 이벤트 로그는 접을 수 있는 section으로 분리한다.
- action button은 44px 이상 높이를 가진다.
- diff는 side-by-side 대신 before -> after 순서로 세로 배치한다.

### Accessibility

- 모든 상태는 색만으로 전달하지 않고 텍스트 라벨을 함께 둔다.
- body text 대비는 4.5:1 이상을 유지한다.
- 키보드 순서는 `status -> summary -> details -> actions -> sources`다.
- action에는 visible label을 둔다. 아이콘만 있는 버튼은 tooltip과 `aria-label`을 가진다.
- form placeholder는 label을 대체할 수 없다.
- link visited 상태는 unvisited와 구분한다.

## Data Contract Implications

디자인 구현은 [07-data-contracts.md](07-data-contracts.md)에 반영된 아래 필드 계약을 따른다.

| 대상 | 필요한 필드 | 이유 |
|---|---|---|
| `ReportDraft.sections[]` | `section_id`, `title`, `status`, `display_order`, `source_refs`, `hidden_reason` | 안전한 부분 출력과 숨긴 섹션을 분리하기 위해 |
| `ReportDraft.actions[]` | `action_id`, `label`, `action_type`, `required_input_schema` | 확인 질문과 재시도 action을 구조화하기 위해 |
| `WikiRevision` | `diff_summary`, `review_actions`, `requested_changes` | 승인 UX에서 before/after와 사용자 결정을 저장하기 위해 |
| `VerificationResult` | `safe_sections`, `hidden_sections`, `required_inputs` | rescue panel을 일관되게 만들기 위해 |
| `RunState` | `current_node`, `last_event_at`, `progress_label` | 긴 실행의 현재 위치를 보여주기 위해 |

이 필드는 문서 계약에 반영되어 있으며, 구현 시 Pydantic 모델과 DB migration에 같은 의미로 옮긴다.

## Copy Rules

| 피해야 할 문구 | 대체 문구 |
|---|---|
| "추천 종목" | "확인할 종목" |
| "매수 신호" | "점검 신호" |
| "목표가" | "추적할 가격 변수" |
| "위험 자산을 늘리세요" | "위험자산 노출을 재점검할 근거" |
| "AI 판단" | "근거 기반 요약" |
| "문제가 없습니다" | "현재 검증 게이트에서 차단 항목이 없습니다" |

문장 원칙:

- 확정형보다 조건형을 우선한다.
- "왜"를 출처와 계산식으로 연결한다.
- 사용자가 할 수 있는 다음 행동을 하나 이상 둔다.
- 투자 조언처럼 보이는 CTA를 만들지 않는다.

## Implementation Tasks

- [ ] **T1 (P1, human: ~2h / CC: ~20min)** - `ReportDraft.sections`와 rescue payload를 Pydantic 모델과 DB schema 구현으로 옮긴다.
  - Surfaced by: Interaction State Coverage
  - Files: app models module, migration file, tests
  - Verify: `safe_sections`, `hidden_sections`, `required_inputs`가 API 응답과 저장 row에서 round-trip 된다.

- [ ] **T2 (P1, human: ~2h / CC: ~20min)** - 포트폴리오 점검 Markdown 템플릿을 구현 스펙으로 옮긴다.
  - Surfaced by: Screen And Document Hierarchy
  - Files: report template module, [06-output-constraints.md](06-output-constraints.md)
  - Verify: `verification_status != passed`일 때 최종 리포트 템플릿이 아니라 rescue 템플릿을 선택한다.

- [ ] **T3 (P2, human: ~2h / CC: ~20min)** - 위키 revision review action payload를 구현한다.
  - Surfaced by: User Journey
  - Files: [01-llmwiki-structure.md](01-llmwiki-structure.md), [07-data-contracts.md](07-data-contracts.md)
  - Verify: approve, reject, request_changes가 모두 audit trail에 남는다.

- [ ] **T4 (P2, human: ~1h / CC: ~10min)** - 실행 상태 조회 응답에 현재 node와 마지막 이벤트를 추가한다.
  - Surfaced by: Responsive And Accessibility
  - Files: [04-langgraph-graphs.md](04-langgraph-graphs.md), [07-data-contracts.md](07-data-contracts.md)
  - Verify: 긴 실행 중 사용자가 현재 단계와 다음 대기 이유를 알 수 있다.

## Acceptance Criteria

- 사용자는 리포트 첫 5초 안에 검증 상태, 기준일, 상위 확인 항목을 볼 수 있다.
- `blocked`와 `needs_human_review`는 최종 리포트처럼 보이지 않는다.
- 모든 주요 숫자 옆에는 계산 근거나 source ref가 있다.
- 위키 revision은 diff, 근거, 검증 결과 없이 승인할 수 없다.
- 부분 실패는 `safe_sections`와 `hidden_sections`로 분리된다.
- 모바일에서 diff와 표는 내용을 잃지 않고 읽힌다.
- 색만으로 상태를 전달하지 않는다.
