# LLMwiki 구조 스펙

## 네임스페이스 설계

```
/wiki/books
  /principles
  /risk-management
  /position-sizing
  /psychology

/wiki/journal
  /winning-patterns
  /mistake-patterns
  /emotion-driven-trades
  /postmortems

/wiki/portfolio
  /current
  /allocation
  /risk-exposure
  /change-history

/wiki/assets
  /{ticker}
  /{ticker}/thesis
  /{ticker}/events
  /{ticker}/risks

/wiki/rules
  /buy-checklist
  /sell-checklist
  /rebalance-rules
  /invalidation-rules
```

## 각 위키 페이지 필수 구성 요소

| 항목 | 설명 |
|---|---|
| **정의** | 이 개념 / 종목 / 원칙이 무엇인지 |
| **출처** | 책, 매매일지, 리포트, 뉴스, 공시 |
| **내 투자와 연결** | 내 매매 패턴 또는 현재 포트폴리오와의 관련성 |
| **충돌 / 위험 신호** | 원칙과 현재 상태가 어긋나는 지점 |
| **확인할 항목** | 다음 점검 때 다시 볼 질문 |

## 공통 페이지 메타데이터

모든 위키 페이지는 사람이 읽는 본문과 별개로 아래 메타데이터를 가져야 한다.

| 필드 | 설명 |
|---|---|
| `page_id` | 안정적인 내부 ID. 제목 변경과 무관하게 유지한다. |
| `page_type` | `principle`, `trade_pattern`, `asset`, `portfolio`, `rule`, `market_regime` 중 하나. |
| `title` | 사용자가 보는 페이지 제목. |
| `source_refs` | 원문 chunk, 매매일지, 리포트, 뉴스, 공시 등 출처 ID 목록. |
| `confidence` | 현재 페이지 내용의 신뢰도. `high`, `medium`, `low` 중 하나. |
| `last_reviewed_at` | Agent 또는 사용자가 마지막으로 검토한 시각. |
| `open_questions` | 다음 점검에서 다시 확인할 질문 목록. |

## 페이지 타입별 추가 필드

| 타입 | 추가 필드 |
|---|---|
| `principle` | 원칙 문장, 적용 조건, 예외 조건, 관련 실수 패턴 |
| `trade_pattern` | 반복 행동, 발생 조건, 손익 영향, 재발 방지 질문 |
| `asset` | ticker, thesis, 핵심 이벤트, 리스크, thesis 무효화 조건 |
| `portfolio` | 기준일, 보유 종목, 비중, 집중도, 현금 비중 |
| `rule` | 체크리스트, 통과 조건, 보류 조건, 충돌하는 규칙 |
| `market_regime` | 국면 정의, 관찰 지표, 포트폴리오 노출 연결 |

## Revision 계약

Agent는 위키 페이지를 바로 덮어쓰지 않는다. 모든 변경은 revision 제안으로 생성한다.

| 상태 | 의미 |
|---|---|
| `draft` | Agent가 생성했지만 검증 전인 초안 |
| `verified` | 숫자, citation, 금지 표현 검사를 통과한 초안 |
| `needs_human_review` | 출처 부족, 해석 불확실, 충돌 항목 때문에 사람 확인이 필요한 초안 |
| `rejected` | 근거 부족 또는 정책 위반으로 폐기된 초안 |
| `accepted` | 사용자가 승인해 현재 위키에 반영된 revision |

Revision에는 `revision_id`, `page_id`, `change_summary`, `before_refs`, `after_refs`, `diff_summary`, `verification_result_id`, `review_actions`, `requested_changes`, `created_by_agent`, `created_at`을 남긴다.

사용자 검토 action은 `approve`, `reject`, `request_changes` 중 하나다. `approve`가 기록되기 전까지 현재 위키 본문은 바뀌지 않는다.

## PostgreSQL 저장 계약

위키의 canonical 저장소는 PostgreSQL이다.

| 위키 개념 | PostgreSQL 테이블 |
|---|---|
| 현재 승인된 페이지 | `wiki_pages` |
| 변경 제안과 승인 이력 | `wiki_revisions` |
| 원문과 citation 근거 | `source_documents`, `chunks` |

Markdown 파일은 사람이 읽기 위한 export 형식으로만 사용한다. Agent가 위키를 갱신할 때는 `wiki_revisions` row를 만들고, 사용자가 승인한 뒤 `wiki_pages.current_revision_id`와 `wiki_pages.body`를 갱신한다.

## 위키 성격 정의

> 위키는 "추천을 저장하는 공간"이 아니라  
> **"근거, 원칙, 관찰, 복기, 현재 상태를 연결하는 공간"**이다.

## 계층 내 역할 구분

| 구분 | LLMwiki |
|---|---|
| 정체 | 지식베이스 / 위키 / memory |
| 예시 | "손절 기준 없는 진입" 페이지 |
| 상태 | 장기 저장됨 |
| 변경 주체 | Agent가 revision으로 갱신 제안 |
| 성공 기준 | 정확하고 연결된 지식 구조 |
