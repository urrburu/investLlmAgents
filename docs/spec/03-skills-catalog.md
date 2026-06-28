# Skills 카탈로그

Skills는 Agent가 필요 시 호출하는 단위 기능이다. 보통 stateless하며 입력 → 출력 구조를 가진다.

## RAG Skills

| Skill | 설명 |
|---|---|
| `parse_document` | PDF·메모 등 원문 파싱 |
| `chunk_document` | 청킹 |
| `embed_chunks` | 임베딩 생성 및 PostgreSQL/pgvector 저장 |
| `retrieve_related_chunks` | 유사 chunk 검색 |
| `rerank_context` | 검색 결과 재정렬 |

## Portfolio Skills

| Skill | 설명 |
|---|---|
| `normalize_ticker` | 티커 정규화 |
| `fetch_price_data` | 가격 데이터 조회 |
| `calculate_returns` | 수익률 계산 |
| `calculate_weights` | 비중 계산 |
| `detect_concentration` | 집중도 감지 |

## Knowledge Skills

| Skill | 설명 |
|---|---|
| `extract_principles` | 투자 원칙 추출 |
| `extract_trade_patterns` | 매매 패턴 추출 |
| `link_rule_to_trade` | 규칙과 매매 연결 |
| `detect_rule_conflict` | 원칙 충돌 감지 |
| `create_wiki_revision` | 위키 revision 생성 |

## Verification Skills

| Skill | 설명 |
|---|---|
| `verify_numbers` | 숫자 검증 |
| `verify_citations` | citation 검증 |
| `check_unsupported_claims` | 근거 없는 주장 탐지 |
| `check_recommendation_language` | 금지 표현 검사 |
| `check_stale_data` | 오래된 가격/뉴스/공시 데이터 탐지 |
| `assess_rag_confidence` | 검색된 근거의 충분성 평가 |
| `quality_score` | 품질 점수 산출 |

## Report Skills

| Skill | 설명 |
|---|---|
| `generate_stock_snapshot` | 종목 Snapshot 생성 |
| `generate_portfolio_report` | 포트폴리오 리포트 생성 |
| `generate_daily_check` | 일간 점검 리포트 생성 |
| `generate_weekly_review` | 주간 리뷰 생성 |
| `format_persona_output` | Persona 스타일 포맷팅 |

## Data Skills

| Skill | 설명 |
|---|---|
| `fetch_news` | 뉴스 수집 |
| `fetch_filings` | 공시 수집 |
| `fetch_financials` | 재무 데이터 조회 |
| `load_journal_entries` | 매매일지 로드 |
| `load_current_holdings` | 현재 보유 종목 로드 |

## Market Regime Skills

| Skill | 설명 |
|---|---|
| `fetch_market_indices` | 시장 지수 조회 |
| `fetch_macro_indicators` | 매크로 지표 수집 |
| `analyze_sector_rotation` | 섹터 로테이션 분석 |
| `detect_risk_on_off` | Risk-on/Risk-off 판단 |
| `generate_market_brief` | 시황 브리프 생성 |

## 계층 내 역할 구분

| 구분 | Skill |
|---|---|
| 정체 | 하나의 호출 가능한 기능 |
| 예시 | 수익률 계산 함수, 문서 임베딩 함수 |
| 상태 | 보통 stateless, 입력 → 출력 |
| 변경 주체 | Agent가 필요 시 호출 |
| 성공 기준 | 정확한 단일 기능 수행 |

## Skill 공통 I/O 계약

Skill은 프롬프트 문자열이 아니라 구조화된 입력과 출력을 주고받는다.

| 항목 | 계약 |
|---|---|
| 입력 | 필요한 데이터, 실행 옵션, `run_id`, `source_refs` |
| 출력 | `status`, `data`, `warnings`, `source_refs`, `error` |
| 오류 | 예외를 삼키지 않고 이름 있는 오류 코드로 반환 |
| 부작용 | 기본은 stateless. 저장이 필요한 Skill은 PostgreSQL table과 revision/report ID를 명시 |
| 검증성 | 계산식, 사용한 원천 데이터, timestamp를 추적 가능하게 남김 |

## Skill 부작용 등급

| 등급 | 의미 | 예시 |
|---|---|---|
| `pure` | 입력만으로 결과를 계산하고 외부 상태를 바꾸지 않음 | `calculate_returns`, `calculate_weights` |
| `read_external` | 외부 API나 파일을 읽지만 저장하지 않음 | `fetch_news`, `fetch_price_data` |
| `propose_revision` | 저장 전 검토가 필요한 변경 제안을 만듦 | `create_wiki_revision` |
| `write_internal` | PostgreSQL 내부 테이블, 캐시, 벡터 컬럼에 기록 | `embed_chunks` |

`write_internal` 이상의 Skill은 실행 로그에 입력 요약, PostgreSQL table/row ID, 되돌릴 수 있는 방법을 남긴다.
