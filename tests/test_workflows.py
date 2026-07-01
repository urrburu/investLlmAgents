from unittest import TestCase

from invest_llm_agents.common.enums import SkillEffect, SkillStatus
from invest_llm_agents.common.skill import SkillInput
from invest_llm_agents.workflows import (
    run_market_judgment,
    run_portfolio_judgment,
    run_stock_analysis,
)


AS_OF = "2026-06-30T00:00:00+00:00"


class WorkflowGraphTests(TestCase):
    def test_stock_analysis_workflow_runs_catalog_skills(self):
        output = run_stock_analysis(
            SkillInput(
                run_id="workflow_stock",
                options={
                    "ticker": "aapl",
                    "now": AS_OF,
                    "prices": [{"ticker": "AAPL", "price": 200, "as_of": AS_OF}],
                    "financials": {"revenue": 100, "as_of": AS_OF},
                    "news": [{"ticker": "AAPL", "title": "AAPL update", "as_of": AS_OF}],
                    "filings": [{"ticker": "AAPL", "title": "10-Q", "as_of": AS_OF}],
                    "query": "AAPL risk valuation",
                    "chunks": [{"chunk_id": "chunk_1", "text": "AAPL valuation risk remains manageable."}],
                },
            )
        )

        self.assertEqual(output.status, SkillStatus.SUCCESS)
        self.assertEqual(output.effect, SkillEffect.READ_EXTERNAL)
        self.assertEqual(output.data["workflow"], "stock_analysis")
        self.assertEqual(output.data["ticker"], "AAPL")
        self.assertEqual(output.data["report"]["report_type"], "stock_snapshot")
        self.assertIn("generate_stock_snapshot", output.data["steps"])

    def test_market_judgment_workflow_runs_catalog_skills(self):
        output = run_market_judgment(
            SkillInput(
                run_id="workflow_market",
                options={
                    "now": AS_OF,
                    "indices": [{"name": "S&P 500", "value": 5500, "return": 0.02, "as_of": AS_OF}],
                    "macro_indicators": [
                        {"name": "vix", "value": 15, "as_of": AS_OF},
                        {"name": "credit_spread", "value": -0.1, "as_of": AS_OF},
                    ],
                    "sector_returns": [
                        {"sector": "Technology", "return": 0.03},
                        {"sector": "Utilities", "return": -0.01},
                    ],
                    "signals": {"equity_return": 0.02, "vix": 15, "credit_spread": -0.1},
                },
            )
        )

        self.assertEqual(output.status, SkillStatus.SUCCESS)
        self.assertEqual(output.data["workflow"], "market_judgment")
        self.assertEqual(output.data["regime"]["regime"], "risk_on")
        self.assertIn("# Market Brief", output.data["brief"]["markdown"])
        self.assertIn("generate_market_brief", output.data["steps"])

    def test_portfolio_judgment_workflow_uses_holdings_without_separate_prices(self):
        output = run_portfolio_judgment(
            SkillInput(
                run_id="workflow_portfolio",
                options={
                    "now": AS_OF,
                    "cash": 100,
                    "holdings": [
                        {
                            "ticker": "AAPL",
                            "quantity": 10,
                            "market_price": 20,
                            "cost_basis": 15,
                            "sector": "Technology",
                            "as_of": AS_OF,
                        },
                        {
                            "ticker": "MSFT",
                            "quantity": 5,
                            "market_price": 20,
                            "cost_basis": 18,
                            "sector": "Technology",
                            "as_of": AS_OF,
                        },
                    ],
                },
            )
        )

        self.assertEqual(output.status, SkillStatus.SUCCESS)
        self.assertEqual(output.data["workflow"], "portfolio_judgment")
        self.assertEqual(output.data["weights"]["total_value"], 400.0)
        self.assertTrue(output.data["concentration"]["is_concentrated"])
        self.assertTrue(output.data["step_outputs"]["fetch_price_data"]["data"]["skipped"])
        self.assertEqual(output.data["report"]["report_type"], "portfolio_report")
