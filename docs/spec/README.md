# Spec 문서 인덱스

[`llmwiki_agent_skills_architecture(1).html`](../llmwiki_agent_skills_architecture%281%29.html)을 기능 영역별로 분리한 스펙 문서 모음.

처음 구현하는 개발자는 루트 [README.md](../../README.md)의 Quickstart로 서버를 띄운 뒤, 아래 순서로 읽는다.

1. [00-overview.md](00-overview.md)로 제품 경계와 계층 구조를 이해한다.
2. [07-data-contracts.md](07-data-contracts.md)로 Pydantic 모델, 상태 enum, PostgreSQL table mapping을 먼저 만든다.
3. [04-langgraph-graphs.md](04-langgraph-graphs.md)로 Graph node와 Skill 매핑을 구현한다.
4. [08-verification-and-safety.md](08-verification-and-safety.md)로 검증 실패와 사용자 rescue 응답을 맞춘다.
5. [09-product-design.md](09-product-design.md)로 사용자에게 보이는 리포트, 승인 흐름, 실패 상태를 맞춘다.
6. [TODOS.md](TODOS.md)에서 아직 결정되지 않은 스케줄러, 데이터 공급원, 구현 작업을 확인한다.

| 파일 | 내용 |
|---|---|
| [00-overview.md](00-overview.md) | 시스템 한 문장 정의, 세 계층 요약, 핵심 원칙 |
| [01-llmwiki-structure.md](01-llmwiki-structure.md) | 위키 네임스페이스 설계, 페이지 필수 구성 요소 |
| [02-agents.md](02-agents.md) | Agent 목록, Trigger, 읽는 지식, 호출 Skills, 출력 |
| [03-skills-catalog.md](03-skills-catalog.md) | RAG·Portfolio·Knowledge·Verification·Report·Data·Market Regime Skills 전체 목록 |
| [04-langgraph-graphs.md](04-langgraph-graphs.md) | Graph 1~5 노드 흐름 정의 |
| [05-execution-flows.md](05-execution-flows.md) | Flow A(위키 갱신), Flow B(포트폴리오 점검), Flow C(시황 분석), Flow D(종목 Snapshot), Flow E(검증 루프) 단계별 흐름 |
| [06-output-constraints.md](06-output-constraints.md) | 허용/금지 출력, MVP 1~3 경계, 구현 우선순위 |
| [07-data-contracts.md](07-data-contracts.md) | 위키, 포트폴리오, 리포트, 검증 결과의 데이터 계약과 PostgreSQL 테이블 매핑 |
| [08-verification-and-safety.md](08-verification-and-safety.md) | 검증 게이트, 실패 처리, 금지 표현, 관측 이벤트 |
| [09-product-design.md](09-product-design.md) | 사용자-facing 리포트 구조, revision 승인 UX, 상태 표현, 접근성 기준 |
| [TODOS.md](TODOS.md) | 뒤로 미룬 범위, 열린 결정, 구현 전 확인할 질문 |
