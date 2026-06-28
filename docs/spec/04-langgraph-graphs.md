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
  → if needs_review: return_review_required
  → if blocked: return_blocked_with_reasons
```

검증 Graph를 우회해 최종 응답으로 가는 경로는 허용하지 않는다. 부분 실패가 발생하면 Graph state에 `warnings`, `missing_inputs`, `blocked_reasons`를 남긴다.

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
  → verify_citations
  → if verified: save_revision_as_pending_acceptance
  → if not verified: mark_revision_needs_human_review
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
  → verify_numbers
  → verify_citations
  → format_response
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
  → verify_numbers
  → verify_claims
  → format_response
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
  → verify_market_claims
```

## Graph 5 · Verification Graph

**Trigger:** 모든 리포트 생성 후 자동 실행

```
draft_report
  → check_numbers_against_metrics
  → check_claims_against_sources
  → check_stale_data
  → check_recommendation_language
  → assess_rag_confidence
  → assign_quality_score
  → approve_or_request_revision
```

## Error Flow

```
node_error
  → classify_error
  → attach_error_to_graph_state
  → decide_recoverability
  → if recoverable: continue_with_warning
  → if needs_user_input: return_review_required
  → if unsafe_or_unverifiable: block_final_output
```
