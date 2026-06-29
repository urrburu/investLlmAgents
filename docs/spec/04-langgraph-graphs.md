# LangGraph Graph 설계

LangGraph 기준으로 작업 유형별 Graph를 분리한다.

## 공통 Graph 게이트

모든 Graph는 아래 게이트를 공유한다.

```
trigger
  → validate_input
  → execute_domain_steps
  → run_verification_graph
  → if verification_passed: format_response
  → if needs_human_review: return_review_required
  → if blocked: return_blocked_with_reasons
```

검증 Graph를 우회해 최종 응답으로 가는 경로는 허용하지 않는다. 부분 실패가 발생하면 Graph state에 `warnings`, `missing_inputs`, `blocked_reasons`를 남긴다. 상태 enum은 [07-data-contracts.md](07-data-contracts.md)의 Canonical 상태 enum을 사용한다.

## 공통 Graph state 최소 필드

```python
class AgentRunState(TypedDict, total=False):
    run_id: str
    agent_name: str
    trigger_type: str
    input_refs: list[str]
    intermediate_artifacts: list[str]
    report_id: str | None
    revision_id: str | None
    verification_result_id: str | None
    verification_status: str
    current_node: str | None
    last_event_at: str | None
    progress_label: str | None
    warnings: list[str]
    missing_inputs: list[str]
    blocked_reasons: list[str]
```

Graph 실행 상태는 PostgreSQL의 `agent_runs` table에 저장한다. 긴 실행 중간 산출물은 `intermediate_artifacts`와 `artifact_ids`에 ID로 연결하고, 실제 report/revision/verification payload는 각 전용 table에 저장한다.

## Node와 Skill 매핑

Graph node는 orchestration 단위이고, Skill은 실제 호출 가능한 단위 기능이다. node가 여러 Skill을 묶는 경우 composite로 표기한다.

| Graph node | 호출 Skill | 설명 |
|---|---|---|
| `parse_document` | `parse_document` | PDF, 메모, 리포트 원문 파싱 |
| `chunk_document` | `chunk_document` | 원문을 citation 가능한 chunk로 분리 |
| `embed_chunks` | `embed_chunks` | chunk 임베딩 생성과 벡터 저장 |
| `extract_principles_or_patterns` | `extract_principles`, `extract_trade_patterns` | 투자 원칙과 반복 매매 패턴 추출 |
| `retrieve_existing_wiki` | `retrieve_related_chunks` | 기존 위키와 관련 chunk 검색 |
| `generate_wiki_revision` | `create_wiki_revision` | 새 위키 revision 제안 생성 |
| `fetch_market_data` | `fetch_price_data`, `fetch_market_indices` | 포트폴리오 계산에 필요한 가격/시장 데이터 조회 |
| `calculate_metrics` | `calculate_returns`, `calculate_weights`, `detect_concentration` | 수익률, 비중, 집중도 계산 |
| `fetch_price_financial_news` | `fetch_price_data`, `fetch_financials`, `fetch_news`, `fetch_filings` | 종목 Snapshot용 composite node |
| `run_verification_graph` | `verify_numbers`, `verify_citations`, `check_unsupported_claims`, `check_recommendation_language`, `check_stale_data`, `assess_rag_confidence`, `quality_score` | 최종 출력 승격 전 공통 검증 |

## Graph 1 · Wiki Indexing Graph

**Trigger:** 책·매매일지·문서 업로드

```
ingest_source
  → validate_source_metadata
  → parse_document
  → chunk_document
  → embed_chunks
  → extract_principles_or_patterns
  → retrieve_existing_wiki
  → generate_wiki_revision
  → run_verification_graph
  → if passed: save_revision_as_pending_acceptance
  → if needs_human_review: mark_revision_needs_human_review
  → if blocked: reject_revision_with_reasons
```

## Graph 2 · Portfolio Review Graph

**Trigger:** 스케줄(일간/주간) 또는 수동 실행

```
scheduled_or_manual_trigger
  → validate_portfolio_snapshot
  → load_current_portfolio
  → fetch_market_data
  → calculate_metrics
  → retrieve_wiki_context
  → detect_rule_conflicts
  → generate_status_report
  → run_verification_graph
  → if passed: format_response
  → if needs_human_review: return_review_required
  → if blocked: return_blocked_with_reasons
```

## Graph 3 · Stock Snapshot Graph

**Trigger:** 사용자의 종목 분석 요청

```
stock_request
  → normalize_ticker
  → resolve_ticker_ambiguity
  → fetch_price_financial_news
  → retrieve_asset_wiki
  → retrieve_related_rules
  → generate_stock_snapshot
  → run_verification_graph
  → if passed: format_response
  → if needs_human_review: return_review_required
  → if blocked: return_blocked_with_reasons
```

## Graph 4 · Market Regime Graph

**Trigger:** 매일 장전/장후 또는 사용자 요청

```
market_check_trigger
  → fetch_indices_rates_fx_volatility
  → fetch_sector_and_factor_rotation
  → calculate_market_regime_signals
  → detect_risk_on_off
  → if mixed_or_insufficient: mark_regime_uncertain
  → retrieve_market_wiki_context
  → connect_to_portfolio_exposure
  → generate_market_brief
  → run_verification_graph
  → if passed: format_response
  → if needs_human_review: return_review_required
  → if blocked: return_blocked_with_reasons
```

## Graph 5 · Verification Graph

**Trigger:** 모든 리포트 생성 후 자동 실행

```
draft_report
  → verify_numbers
  → verify_citations
  → check_unsupported_claims
  → check_stale_data
  → check_recommendation_language
  → assess_rag_confidence
  → quality_score
  → approve_or_request_revision
```

## Error Flow

```
node_error
  → classify_error
  → attach_error_to_graph_state
  → decide_recoverability
  → if recoverable: continue_with_warning
  → if needs_human_review: return_review_required
  → if unsafe_or_unverifiable: block_final_output
```
