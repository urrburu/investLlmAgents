from decimal import Decimal
from unittest import TestCase

from invest_llm_agents.common.enums import (
    ErrorCode,
    ReportType,
    VerificationStatus,
)
from invest_llm_agents.common.models import (
    PortfolioHolding,
    ReportDraft,
    VerificationResult,
)
from invest_llm_agents.common.renderers import render_report_or_rescue
from invest_llm_agents.common.skill import SkillOutput
from invest_llm_agents.common.verification import (
    check_recommendation_language,
    report_can_be_promoted,
)


class CommonContractTests(TestCase):
    def test_forbidden_recommendation_language_is_blocked(self):
        checks = check_recommendation_language("지금 매수해야 한다")

        self.assertGreaterEqual(len(checks), 1)
        self.assertEqual(checks[0]["status"], VerificationStatus.BLOCKED)
        self.assertEqual(checks[0]["error_code"], ErrorCode.UNSUPPORTED_RECOMMENDATION)

    def test_report_requires_passed_report_and_verification(self):
        report = ReportDraft(
            report_id="report_001",
            report_type=ReportType.PORTFOLIO_REPORT,
            title="포트폴리오 점검",
            verification_status=VerificationStatus.PASSED,
        )
        verification = VerificationResult(
            verification_result_id="verify_001",
            target_id="report_001",
            status=VerificationStatus.PASSED,
            quality_score=90,
        )

        self.assertTrue(report_can_be_promoted(report, verification))

    def test_unpassed_report_renders_rescue(self):
        report = ReportDraft(
            report_id="report_001",
            report_type=ReportType.PORTFOLIO_REPORT,
            title="포트폴리오 점검",
            verification_status=VerificationStatus.NEEDS_HUMAN_REVIEW,
        )
        verification = VerificationResult(
            verification_result_id="verify_001",
            target_id="report_001",
            status=VerificationStatus.NEEDS_HUMAN_REVIEW,
            required_inputs=["출처를 추가합니다."],
            quality_score=72,
        )

        rendered = render_report_or_rescue(report, verification)

        self.assertIn("# 검토가 필요한 결과입니다", rendered)
        self.assertIn("출처를 추가합니다.", rendered)

    def test_skill_blocked_output_uses_named_error_code(self):
        output = SkillOutput.blocked(
            ErrorCode.NUMBER_MISMATCH,
            "계산 결과가 원천 데이터와 일치하지 않습니다.",
        )

        self.assertEqual(output.status, "blocked")
        self.assertIsNotNone(output.error)
        self.assertEqual(output.error.error_code, ErrorCode.NUMBER_MISMATCH)

    def test_portfolio_holding_weight_is_bounded(self):
        holding = PortfolioHolding(
            ticker="AAPL",
            quantity=Decimal("10"),
            market_value=Decimal("1952.00"),
            weight=Decimal("0.34"),
            data_status="complete",
        )

        self.assertEqual(holding.weight, Decimal("0.34"))
