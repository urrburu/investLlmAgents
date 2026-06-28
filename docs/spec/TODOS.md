# Spec TODOs

이 문서는 CEO 리뷰에서 의도적으로 뒤로 미룬 범위와 구현 전 확인해야 할 결정을 보관한다.

## 확정 결정

| 결정 | 내용 | 반영 위치 |
|---|---|---|
| DB | PostgreSQL을 canonical 저장소로 사용한다. | [07-data-contracts.md](07-data-contracts.md) |
| 위키 저장 | 위키 페이지와 revision은 DB row로 저장한다. Markdown은 export 형식이다. | [01-llmwiki-structure.md](01-llmwiki-structure.md) |
| Graph state | Agent 실행 상태는 `agent_runs` table에 저장한다. | [04-langgraph-graphs.md](04-langgraph-graphs.md) |

## 뒤로 미룬 범위

| 항목 | 이유 | 다시 볼 시점 |
|---|---|---|
| 브로커 주문 API와 자동매매 | 제품 경계가 투자 점검에서 자동 의사결정으로 넘어감 | MVP 3 이후 별도 안전/권한 설계 시 |
| 목표가/매수/매도 추천 UX | 현황 점검이라는 핵심 포지셔닝과 충돌 | 법률/컴플라이언스 검토 후 |
| 세금 최적화 | 사용자 국가, 계좌 유형, 세법이 복잡함 | 포트폴리오 데이터 모델 안정화 후 |
| 파생상품 분석 | MVP의 지식 구조와 검증 복잡도를 크게 늘림 | 현물/ETF 흐름이 안정화된 뒤 |
| 다중 사용자 권한 모델 | 개인 투자 메모리 제품의 초기 학습을 늦춤 | 공유/팀 기능 요구가 생긴 뒤 |

## 열린 결정

| 결정 | 현재 가정 | 확인 필요 |
|---|---|---|
| 벡터 저장 | PostgreSQL `pgvector` 우선 | embedding dimension, index 방식, 확장 설치 가능 여부 |
| 가격 데이터 공급원 | MVP에서는 교체 가능한 adapter로 감쌈 | 사용자가 실제로 접근 가능한 API |
| 스케줄러 | 일간/주간 실행만 가정 | 로컬 cron, GitHub Actions, 서버 배치 중 선택 |
| 승인 UX | revision row를 사람이 승인한다고 가정 | CLI, 웹 UI, DB-backed diff 중 어떤 흐름이 좋은지 |

## 구현 전 질문

- 사용자의 포트폴리오 입력은 CSV, 수동 Markdown, API 중 무엇을 1차로 볼 것인가?
- 투자서 PDF와 매매일지 중 어느 원천을 먼저 넣을 것인가?
- PostgreSQL schema migration 도구는 Alembic으로 갈 것인가, SQL 파일 기반으로 시작할 것인가?
- `pgvector`를 MVP에 바로 포함할 것인가, 아니면 `embedding_id`만 남기고 검색 저장소를 뒤로 미룰 것인가?
- 최종 리포트는 Markdown 파일, 웹 화면, 채팅 응답 중 어디에 먼저 출력할 것인가?
- 검증 실패 리포트는 사용자에게 얼마나 자세히 보여줄 것인가?

## 다음 구현 작업 후보

1. [07-data-contracts.md](07-data-contracts.md)의 Pydantic 모델 초안을 실제 `app/models` 또는 `invest_llm_agents/models` 모듈로 옮긴다.
2. PostgreSQL schema migration을 작성한다: `source_documents`, `chunks`, `wiki_pages`, `wiki_revisions`, `portfolio_snapshots`, `portfolio_holdings`, `report_drafts`, `verification_results`, `agent_runs`.
3. `SourceDocument`, `Chunk`, `WikiPage`, `WikiRevision`, `PortfolioSnapshot`, `VerificationResult`, `RunState`의 단위 테스트를 작성한다.
4. 포트폴리오 CSV 샘플 스키마와 `validate_portfolio_snapshot` 검증 함수를 작성한다.
5. [04-langgraph-graphs.md](04-langgraph-graphs.md)의 Node와 Skill 매핑을 기준으로 Wiki Indexing Graph happy path를 프로토타입으로 만든다.
6. Verification Graph의 `verify_citations`, `check_unsupported_claims`, `check_recommendation_language` 프로토타입을 작성한다.
7. [08-verification-and-safety.md](08-verification-and-safety.md)의 rescue payload 예시를 반환하는 실패 케이스 테스트를 추가한다.
8. 포트폴리오 점검 리포트 Markdown 템플릿을 작성하고 `verification_status != passed`일 때는 검토 요청 템플릿으로 분기한다.

## 문서 유지 규칙

- 새 상태값은 [07-data-contracts.md](07-data-contracts.md)의 Canonical 상태 enum에 먼저 추가한다.
- 새 DB table이나 column은 [07-data-contracts.md](07-data-contracts.md)의 PostgreSQL 저장소 계약에 먼저 추가한다.
- 새 Graph node는 [04-langgraph-graphs.md](04-langgraph-graphs.md)의 Node와 Skill 매핑에 추가한다.
- 새 오류 코드는 [08-verification-and-safety.md](08-verification-and-safety.md)의 Error & Rescue Registry와 payload 예시에 추가한다.
- 루트 [README.md](../../README.md)의 Quickstart는 실제로 실행 가능한 명령만 둔다.
