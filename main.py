from fastapi import FastAPI
from pydantic import BaseModel, Field

from invest_llm_agents.common.enums import (
    ErrorCode,
    VerificationStatus,
    WikiRevisionStatus,
    RunStatus,
    TriggerType,
    RevisionReviewAction,
)
from invest_llm_agents.common.renderers import render_rescue
from invest_llm_agents.common.verification import (
    build_rescue_payload,
    check_recommendation_language,
)

app = FastAPI()


class LanguageCheckRequest(BaseModel):
    text: str = Field(min_length=1)


@app.get("/")
async def root():
    return {
        "message": "Hello World",
        "service": "investLlmAgents",
        "purpose": "검증 가능한 개인 투자 점검 백엔드",
        "common_contracts": "/contracts/enums",
        "verification_check": "/verification/language-check",
    }


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/contracts/enums")
async def contract_enums():
    return {
        "verification_status": [item.value for item in VerificationStatus],
        "wiki_revision_status": [item.value for item in WikiRevisionStatus],
        "run_status": [item.value for item in RunStatus],
        "trigger_type": [item.value for item in TriggerType],
        "revision_review_action": [item.value for item in RevisionReviewAction],
        "error_code": [item.value for item in ErrorCode],
    }


@app.post("/verification/language-check")
async def language_check(payload: LanguageCheckRequest):
    checks = check_recommendation_language(payload.text)
    status = VerificationStatus.BLOCKED if checks else VerificationStatus.PASSED
    return {
        "verification_status": status,
        "checks": checks,
        "required_fixes": [
            "매수/매도 지시, 목표가, 보장 표현을 확인 질문 또는 조건형 표현으로 바꿉니다."
        ]
        if checks
        else [],
    }


@app.get("/verification/rescue-example")
async def rescue_example():
    payload = build_rescue_payload(
        error_code=ErrorCode.NUMBER_MISMATCH,
        message="포트폴리오 비중 계산 결과가 원천 데이터와 일치하지 않습니다.",
        blocked_reasons=[
            "AAPL market_value와 total_portfolio_value 계산에 사용된 값이 다릅니다."
        ],
        required_inputs=[
            "최신 포트폴리오 CSV를 다시 업로드하거나 market_value 계산 로그를 확인합니다."
        ],
        hidden_sections=["portfolio_weights", "return_summary"],
    )
    return {
        "payload": payload,
        "markdown": render_rescue(payload),
    }
