# investLlmAgents

개인 투자 원칙, 매매일지, 포트폴리오, 시장 데이터를 연결해 검증 가능한 투자 점검 리포트를 만드는 FastAPI + LangGraph 기반 백엔드입니다.

이 프로젝트는 투자 추천 엔진이 아닙니다. 목표는 "무엇을 사라"가 아니라 "내 원칙, 과거 실수, 현재 보유 노출이 어디서 충돌하는지"를 근거와 함께 보여주는 작업대입니다.

## 3분 Quickstart

### 필요한 것

- Python 3.12 이상
- `uv`

### 실행

```powershell
uv sync
uv run uvicorn main:app --reload
```

서버가 뜨면 아래 주소를 확인합니다.

- API root: http://127.0.0.1:8000/
- FastAPI docs: http://127.0.0.1:8000/docs

기대 응답:

```json
{"message":"Hello World"}
```

`test_main.http`를 지원하는 IDE에서는 [test_main.http](test_main.http)를 열고 두 요청을 바로 실행할 수 있습니다.

## 첫 구현 목표

현재 코드는 FastAPI 기본 엔드포인트만 가진 초기 상태입니다. 스펙 기준 첫 구현은 아래 순서로 진행합니다.

1. [데이터 계약](docs/spec/07-data-contracts.md)의 Pydantic 모델을 만든다.
2. PostgreSQL schema와 migration을 만든다. DB 테이블 매핑은 [데이터 계약](docs/spec/07-data-contracts.md)의 PostgreSQL 저장소 계약을 따른다.
3. [LangGraph Graph 설계](docs/spec/04-langgraph-graphs.md)의 Wiki Indexing happy path를 프로토타입으로 만든다.
4. [검증 및 안전 스펙](docs/spec/08-verification-and-safety.md)의 citation/금지 표현 검사를 먼저 붙인다.
5. [출력 제약 및 MVP 경계](docs/spec/06-output-constraints.md)의 품질 게이트를 통과하지 못하면 최종 리포트로 승격하지 않는다.
6. [제품 디자인 스펙](docs/spec/09-product-design.md)의 Markdown 리포트, revision 승인, rescue 응답 구조를 사용자-facing 출력의 기준으로 삼는다.

## 문서

| 문서 | 역할 |
|---|---|
| [docs/spec/README.md](docs/spec/README.md) | 스펙 문서 인덱스 |
| [docs/langgraph-usage.md](docs/langgraph-usage.md) | LangGraph 기본 사용법과 이 프로젝트 적용 가이드 |
| [docs/spec/00-overview.md](docs/spec/00-overview.md) | 제품 정의와 계층 구조 |
| [docs/spec/04-langgraph-graphs.md](docs/spec/04-langgraph-graphs.md) | Graph 흐름과 node/Skill 매핑 |
| [docs/spec/07-data-contracts.md](docs/spec/07-data-contracts.md) | Agent와 Skill이 공유하는 데이터 계약과 PostgreSQL 테이블 매핑 |
| [docs/spec/08-verification-and-safety.md](docs/spec/08-verification-and-safety.md) | 검증 상태, 오류 코드, rescue payload |
| [docs/spec/09-product-design.md](docs/spec/09-product-design.md) | 사용자-facing 리포트 구조, revision 승인 UX, 상태 표현 |
| [docs/spec/TODOS.md](docs/spec/TODOS.md) | 남은 결정과 다음 구현 작업 |

## 개발자 체크

문서를 수정할 때는 다음을 같이 확인합니다.

- 새 데이터 구조는 [docs/spec/07-data-contracts.md](docs/spec/07-data-contracts.md)에 먼저 정의한다.
- 새 Graph node는 [docs/spec/04-langgraph-graphs.md](docs/spec/04-langgraph-graphs.md)의 node/Skill 매핑에 추가한다.
- 새 오류는 [docs/spec/08-verification-and-safety.md](docs/spec/08-verification-and-safety.md)의 Error & Rescue Registry에 추가한다.
- 최종 사용자에게 보이는 출력은 `verification_status`가 `passed`일 때만 리포트로 승격한다.
