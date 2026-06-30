# LangGraph 사용법 정리

이 문서는 이 프로젝트에서 LangGraph를 어떻게 써야 하는지 빠르게 확인하는 구현 가이드다. 현재 `pyproject.toml`은 `langgraph>=1.2.6`을 사용한다.

LangGraph는 LLM 호출 라이브러리라기보다 **상태를 가진 워크플로우 실행기**로 보는 편이 맞다. 이 프로젝트에서는 포트폴리오 점검, 종목 Snapshot, 위키 revision, 검증 루프를 노드와 엣지로 연결하고, 검증을 통과한 결과만 사용자-facing 출력으로 승격하는 데 쓴다.

## 언제 LangGraph를 쓰나

LangGraph를 쓰기 좋은 경우:

- 여러 단계가 있고 각 단계의 상태를 다음 단계가 읽어야 한다.
- 실패, 재시도, 사용자 승인, 검증 게이트가 실행 흐름 안에 들어간다.
- 긴 실행을 중간 상태로 저장하고 나중에 이어서 실행해야 한다.
- LLM, 계산 코드, 검색, DB 저장 같은 서로 다른 작업을 한 흐름으로 묶어야 한다.

LangGraph를 쓰지 않아도 되는 경우:

- 단일 함수 호출로 끝나는 계산이다.
- 상태 저장이나 분기가 없다.
- 단순 FastAPI CRUD 엔드포인트다.

## 핵심 개념

| 개념 | 의미 | 이 프로젝트 기준 |
|---|---|---|
| State | 그래프 전체가 공유하는 실행 상태 | `RunState`와 같은 실행 계약을 `TypedDict`로 옮겨 사용 |
| Node | 상태를 받아 일부 상태 업데이트를 반환하는 함수 | `validate_input`, `calculate_metrics`, `run_verification_graph` |
| Edge | 다음에 실행할 노드를 정하는 연결 | 고정 순서 또는 상태 기반 분기 |
| Reducer | 같은 state key에 여러 업데이트가 들어올 때 합치는 규칙 | `warnings`, `missing_inputs`, `blocked_reasons`는 append reducer 권장 |
| Checkpointer | 실행 상태 스냅샷 저장 장치 | 개발은 `InMemorySaver`, 운영은 PostgreSQL 계열 saver 검토 |
| Interrupt | 사람 입력이 필요할 때 그래프를 멈추고 재개하는 장치 | 위키 revision 승인, 모호한 티커 확인 |
| Store | thread를 넘어 공유되는 장기 메모리 | 개인 투자 원칙, 사용자 선호는 DB/위키를 canonical로 유지 |

## 기본 설치와 확인

이 레포는 이미 의존성에 LangGraph가 들어 있다.

```powershell
uv sync
uv run python -c "from langgraph.graph import StateGraph; print('ok')"
```

새로운 체크포인터 패키지가 필요하면 별도 의존성을 추가한다. 예를 들어 PostgreSQL 체크포인터를 직접 쓰려면 LangGraph 공식 checkpointer 패키지와 DB 드라이버를 함께 확인해야 한다.

## 가장 작은 Graph 형태

LangGraph의 기본 순서는 `State` 정의, node 함수 작성, `StateGraph`에 node와 edge 등록, `compile()`, `invoke()`다.

```python
import operator
from typing import Annotated, Literal

from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

from invest_llm_agents.common.enums import RunStatus, VerificationStatus


class AgentGraphState(TypedDict, total=False):
    run_id: str
    agent_name: str
    trigger_type: str
    input_refs: list[str]
    current_node: str | None
    progress_label: str | None
    verification_status: str
    status: str
    warnings: Annotated[list[str], operator.add]
    missing_inputs: Annotated[list[str], operator.add]
    blocked_reasons: Annotated[list[str], operator.add]


def validate_input(state: AgentGraphState) -> AgentGraphState:
    if not state.get("input_refs"):
        return {
            "current_node": "validate_input",
            "verification_status": VerificationStatus.NEEDS_HUMAN_REVIEW.value,
            "missing_inputs": ["분석할 입력 소스가 필요합니다."],
        }

    return {
        "current_node": "validate_input",
        "progress_label": "입력 확인 완료",
    }


def generate_report(state: AgentGraphState) -> AgentGraphState:
    return {
        "current_node": "generate_status_report",
        "progress_label": "초안 생성 완료",
    }


def run_verification(state: AgentGraphState) -> AgentGraphState:
    if state.get("missing_inputs"):
        return {"current_node": "run_verification_graph"}

    return {
        "current_node": "run_verification_graph",
        "verification_status": VerificationStatus.PASSED.value,
    }


def route_after_verification(
    state: AgentGraphState,
) -> Literal["format_response", "return_review_required", "return_blocked_with_reasons"]:
    status = state.get("verification_status")

    if status == VerificationStatus.PASSED.value:
        return "format_response"
    if status == VerificationStatus.NEEDS_HUMAN_REVIEW.value:
        return "return_review_required"
    return "return_blocked_with_reasons"


def format_response(state: AgentGraphState) -> AgentGraphState:
    return {
        "status": RunStatus.COMPLETED.value,
        "progress_label": "리포트 생성 완료",
    }


def return_review_required(state: AgentGraphState) -> AgentGraphState:
    return {"status": RunStatus.NEEDS_HUMAN_REVIEW.value}


def return_blocked_with_reasons(state: AgentGraphState) -> AgentGraphState:
    return {"status": RunStatus.BLOCKED.value}


builder = StateGraph(AgentGraphState)
builder.add_node("validate_input", validate_input)
builder.add_node("generate_status_report", generate_report)
builder.add_node("run_verification_graph", run_verification)
builder.add_node("format_response", format_response)
builder.add_node("return_review_required", return_review_required)
builder.add_node("return_blocked_with_reasons", return_blocked_with_reasons)

builder.add_edge(START, "validate_input")
builder.add_edge("validate_input", "generate_status_report")
builder.add_edge("generate_status_report", "run_verification_graph")
builder.add_conditional_edges("run_verification_graph", route_after_verification)
builder.add_edge("format_response", END)
builder.add_edge("return_review_required", END)
builder.add_edge("return_blocked_with_reasons", END)

graph = builder.compile()

result = graph.invoke(
    {
        "run_id": "run_demo",
        "agent_name": "portfolio_review",
        "trigger_type": "manual",
        "input_refs": ["portfolio_csv_001"],
        "verification_status": VerificationStatus.PENDING.value,
    }
)
```

주의할 점:

- node는 전체 state를 반환할 필요가 없다. 바뀐 key만 반환한다.
- reducer가 없는 key는 새 값으로 덮어쓴다.
- `warnings`, `missing_inputs`, `blocked_reasons`처럼 누적되어야 하는 list는 `Annotated[list[str], operator.add]`를 붙인다.
- `compile()` 전에는 그래프를 실행할 수 없다.

## State 설계 원칙

공식 문서 기준으로 state schema는 보통 `TypedDict`를 쓴다. Pydantic 모델도 가능하지만, node가 작은 dict 업데이트를 계속 반환하는 LangGraph 특성상 이 프로젝트에서는 아래 원칙을 권장한다.

1. 그래프 내부 state는 `TypedDict`로 둔다.
2. 외부 입력, DB row, API 응답은 `invest_llm_agents.common.models`의 Pydantic 모델로 검증한다.
3. state에는 큰 본문을 직접 넣지 말고 `report_id`, `revision_id`, `artifact_ids` 같은 ID를 넣는다.
4. 원문, 리포트 본문, 검증 상세 payload는 PostgreSQL 전용 table에 저장한다.

권장 state key:

```python
class AgentGraphState(TypedDict, total=False):
    run_id: str
    agent_name: str
    trigger_type: str
    input_refs: list[str]
    intermediate_artifacts: Annotated[list[str], operator.add]
    artifact_ids: Annotated[list[str], operator.add]
    report_id: str | None
    revision_id: str | None
    verification_result_id: str | None
    verification_status: str
    current_node: str | None
    last_event_at: str | None
    progress_label: str | None
    warnings: Annotated[list[str], operator.add]
    missing_inputs: Annotated[list[str], operator.add]
    blocked_reasons: Annotated[list[str], operator.add]
```

## Node 작성 패턴

node는 작게 유지한다. 한 node는 보통 하나의 orchestration 책임만 가진다.

좋은 node:

- 입력 검증
- 특정 Skill 호출
- 검증 결과를 state로 매핑
- 다음 분기를 위한 status 기록

피해야 할 node:

- 여러 외부 API 호출, DB 쓰기, LLM 호출, 검증, 포맷팅을 한 함수에 몰아넣은 node
- state 전체를 매번 새로 구성하는 node
- 실패했는데 `blocked_reasons`나 `warnings`를 남기지 않는 node

Skill을 감싸는 node 예시:

```python
from invest_llm_agents.common.enums import SkillStatus, VerificationStatus
from invest_llm_agents.common.skill import SkillInput, SkillOutput


def calculate_metrics_skill(payload: SkillInput) -> SkillOutput:
    # 실제 구현에서는 가격 데이터와 포트폴리오 snapshot을 읽어 계산한다.
    return SkillOutput.ok({"artifact_id": "artifact_metrics_001"})


def calculate_metrics_node(state: AgentGraphState) -> AgentGraphState:
    output = calculate_metrics_skill(
        SkillInput(
            run_id=state["run_id"],
            source_refs=[],
            options={"input_refs": state.get("input_refs", [])},
        )
    )

    if output.status == SkillStatus.SUCCESS:
        return {
            "current_node": "calculate_metrics",
            "artifact_ids": [output.data["artifact_id"]],
        }

    if output.status == SkillStatus.NEEDS_HUMAN_REVIEW:
        return {
            "current_node": "calculate_metrics",
            "verification_status": VerificationStatus.NEEDS_HUMAN_REVIEW.value,
            "missing_inputs": output.error.details.get("required_inputs", [])
            if output.error
            else [],
        }

    return {
        "current_node": "calculate_metrics",
        "verification_status": VerificationStatus.BLOCKED.value,
        "blocked_reasons": [output.error.message if output.error else "Skill 실행 실패"],
    }
```

## Edge와 분기

고정 순서라면 `add_edge()`를 쓴다.

```python
builder.add_edge("calculate_metrics", "retrieve_wiki_context")
```

상태를 보고 다음 node를 고른다면 `add_conditional_edges()`를 쓴다.

```python
def route_status(state: AgentGraphState) -> Literal["format_response", "return_blocked"]:
    if state.get("verification_status") == VerificationStatus.PASSED.value:
        return "format_response"
    return "return_blocked"


builder.add_conditional_edges("run_verification_graph", route_status)
```

분기와 state update를 동시에 해야 하면 `Command`를 쓴다.

```python
from typing import Literal

from langgraph.types import Command


def approve_or_block(
    state: AgentGraphState,
) -> Command[Literal["format_response", "return_blocked_with_reasons"]]:
    if state.get("verification_status") == VerificationStatus.PASSED.value:
        return Command(
            update={"progress_label": "검증 통과"},
            goto="format_response",
        )

    return Command(
        update={"blocked_reasons": ["검증을 통과하지 못했습니다."]},
        goto="return_blocked_with_reasons",
    )
```

한 node에서 정적 edge와 동적 분기를 동시에 섞으면 흐름이 헷갈리기 쉽다. 한 node의 다음 경로는 `add_edge`, `add_conditional_edges`, `Command(goto=...)` 중 하나로 명확히 잡는다.

## Checkpointer와 실행 재개

checkpointer는 thread별 graph state 스냅샷을 저장한다. 개발 중에는 메모리 saver로 충분하다.

```python
from langgraph.checkpoint.memory import InMemorySaver


checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": "run_demo"}}
result = graph.invoke(initial_state, config=config)
snapshot = graph.get_state(config)
```

운영에서는 `run_id`를 `thread_id`로 쓰는 방식을 권장한다. PostgreSQL saver를 쓸 때는 `thread_id` 길이 제한을 피하기 위해 UUID 또는 짧은 hash를 사용한다.

이 프로젝트에서 저장소 역할은 둘로 나눈다.

| 저장 대상 | 권장 위치 |
|---|---|
| graph 실행의 최신 state와 재개 지점 | LangGraph checkpointer |
| 리포트, revision, 검증 결과, 원문 artifact | PostgreSQL canonical table |
| 장기 투자 원칙, 위키 page, 사용자 규칙 | LLMwiki/PostgreSQL |

## Human-in-the-loop

사용자 확인이 필요한 지점에서는 `interrupt()`로 그래프를 멈춘다. 재개하려면 같은 `thread_id` config와 `Command(resume=...)`를 넘긴다.

```python
from langgraph.types import Command, interrupt


def request_revision_review(state: AgentGraphState) -> AgentGraphState:
    decision = interrupt(
        {
            "kind": "wiki_revision_review",
            "revision_id": state.get("revision_id"),
            "question": "이 위키 revision을 승인할까요?",
            "options": ["approve", "reject", "request_changes"],
        }
    )

    if decision["action"] == "approve":
        return {"verification_status": VerificationStatus.PASSED.value}

    return {
        "verification_status": VerificationStatus.NEEDS_HUMAN_REVIEW.value,
        "missing_inputs": decision.get("requested_changes", []),
    }


config = {"configurable": {"thread_id": "run_demo"}}
graph.invoke(initial_state, config=config)
graph.invoke(Command(resume={"action": "approve"}), config=config)
```

주의할 점:

- `interrupt()`를 쓰는 그래프는 checkpointer가 필요하다.
- resume 시 interrupt 이전 node가 다시 실행될 수 있으므로, node 안의 외부 side effect는 idempotent하게 만든다.
- 승인 후 DB에 쓰는 작업은 `approve` resume 이후 별도 node에서 수행하는 편이 안전하다.

## Subgraph 사용

검증 그래프는 여러 Agent가 공유한다. 처음에는 함수형 node로 감싸도 되지만, 검증 단계가 커지면 subgraph로 분리한다.

```python
def build_verification_graph():
    builder = StateGraph(AgentGraphState)
    builder.add_node("verify_numbers", verify_numbers)
    builder.add_node("verify_citations", verify_citations)
    builder.add_node("quality_score", quality_score)
    builder.add_edge(START, "verify_numbers")
    builder.add_edge("verify_numbers", "verify_citations")
    builder.add_edge("verify_citations", "quality_score")
    builder.add_edge("quality_score", END)
    return builder.compile()


verification_graph = build_verification_graph()
portfolio_builder.add_node("run_verification_graph", verification_graph)
```

subgraph를 쓸 때는 parent와 subgraph가 공유하는 state key를 명확히 한다. subgraph에서 만든 상세 결과가 parent에서 필요하면 `verification_result_id`처럼 명시적인 key로 올려준다.

## Streaming과 관측

FastAPI에서 진행률을 보여주거나 로그를 남기려면 `stream()` 또는 `stream_events()`를 쓴다.

```python
for update in graph.stream(
    initial_state,
    config={"configurable": {"thread_id": "run_demo"}},
    stream_mode="updates",
):
    print(update)
```

권장 관측 이벤트:

- `agent_run_started`
- `external_data_fetched`
- `verification_failed`
- `report_blocked`
- `revision_proposed`
- `agent_run_completed`

현재 `AgentEvent` 모델이 이미 있으므로, node 안에서는 관측 이벤트를 DB 또는 로그 sink에 남기고 state에는 `last_event_at`, `current_node`, `progress_label`만 짧게 유지한다.

## 테스트 방법

테스트는 세 층으로 나눈다.

1. node 단위 테스트: state dict를 넣고 반환 update를 검증한다.
2. graph happy path 테스트: `graph.invoke()` 결과가 `completed`인지 확인한다.
3. blocked/rescue path 테스트: 입력 누락, 숫자 불일치, 금지 표현에서 `blocked` 또는 `needs_human_review`로 끝나는지 확인한다.

예시:

```python
def test_portfolio_graph_blocks_missing_input():
    graph = build_portfolio_review_graph()

    result = graph.invoke(
        {
            "run_id": "run_test",
            "agent_name": "portfolio_review",
            "trigger_type": "manual",
            "verification_status": "pending",
        }
    )

    assert result["status"] == "needs_human_review"
    assert result["missing_inputs"]
```

checkpointer가 필요한 테스트:

```python
from langgraph.checkpoint.memory import InMemorySaver


def test_revision_review_interrupt_can_resume():
    graph = build_wiki_revision_graph().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "run_review_test"}}

    graph.invoke(initial_state, config=config)
    result = graph.invoke(Command(resume={"action": "approve"}), config=config)

    assert result["verification_status"] == "passed"
```

## 이 프로젝트 구현 순서

1. `invest_llm_agents/graphs/state.py`에 `AgentGraphState`를 둔다.
2. `invest_llm_agents/graphs/verification.py`에 검증 graph builder를 만든다.
3. `invest_llm_agents/graphs/wiki_indexing.py`에 Wiki Indexing happy path를 만든다.
4. 각 node는 `invest_llm_agents/common/skill.py`의 `SkillInput`과 `SkillOutput` 계약을 사용한다.
5. 최종 출력 node는 반드시 `verification_status == "passed"`일 때만 리포트 Markdown을 반환한다.
6. `blocked` 또는 `needs_human_review`는 `render_rescue()` 또는 review-required 응답으로 연결한다.

## 체크리스트

- [ ] graph state에는 큰 본문 대신 ID를 넣었다.
- [ ] 누적 list key에는 reducer를 붙였다.
- [ ] 모든 최종 응답 경로 앞에 `run_verification_graph`가 있다.
- [ ] node 실패는 `warnings`, `missing_inputs`, `blocked_reasons` 중 하나로 남긴다.
- [ ] 외부 side effect가 있는 node는 재실행되어도 같은 결과가 되도록 만들었다.
- [ ] human review가 필요한 graph는 checkpointer와 `thread_id`를 사용한다.
- [ ] 테스트는 happy path와 blocked/rescue path를 둘 다 가진다.

## 공식 문서

- [LangGraph Overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [Graph API overview](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers)
- [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [Streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
- [Testing LangGraph apps](https://docs.langchain.com/oss/python/langgraph/test)
