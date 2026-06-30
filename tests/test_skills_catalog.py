import re
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from invest_llm_agents.common.enums import SkillEffect, SkillStatus
from invest_llm_agents.common.skill import SkillInput
from invest_llm_agents.skills import invoke_skill, list_skills


SKILL_CASES = {
    "parse_document": {"text": "Always define risk before entry.", "title": "Memo"},
    "chunk_document": {"text": "Always define risk before entry.", "chunk_size": 50, "overlap": 0},
    "embed_chunks": {"chunks": [{"chunk_id": "chunk_1", "document_id": "doc_1", "text": "risk first"}], "dimensions": 8},
    "retrieve_related_chunks": {"query": "risk", "chunks": [{"chunk_id": "chunk_1", "text": "risk first"}]},
    "rerank_context": {"query": "risk", "results": [{"chunk_id": "chunk_1", "text": "risk first", "score": 0.5}]},
    "normalize_ticker": {"ticker": "aapl"},
    "fetch_price_data": {"prices": [{"ticker": "AAPL", "price": 200, "as_of": "2026-06-30T00:00:00+00:00"}]},
    "calculate_returns": {"holdings": [{"ticker": "AAPL", "cost_basis": 100, "market_price": 110}]},
    "calculate_weights": {"holdings": [{"ticker": "AAPL", "quantity": 1, "market_price": 100, "cost_basis": 90}]},
    "detect_concentration": {"holdings": [{"ticker": "AAPL", "weight": 0.6, "sector": "Technology"}]},
    "extract_principles": {"text": "Always define risk before entry."},
    "extract_trade_patterns": {"journal_entries": [{"ticker": "AAPL", "action": "buy", "reason": "breakout", "return": 0.1}]},
    "link_rule_to_trade": {
        "rules": [{"rule_id": "rule_1", "text": "avoid chasing breakouts"}],
        "trades": [{"trade_id": "trade_1", "ticker": "AAPL", "reason": "breakout"}],
    },
    "detect_rule_conflict": {
        "rules": [
            {"rule_id": "rule_1", "text": "always diversify growth positions"},
            {"rule_id": "rule_2", "text": "never diversify growth positions"},
        ]
    },
    "create_wiki_revision": {"proposed_body": "Always define risk before entry.", "page_id": "page_1"},
    "verify_numbers": {"numbers": [{"number_id": "n1", "value": 10, "expected": 10, "formula": "provided"}]},
    "verify_citations": {"claims": [{"claim_id": "c1", "text": "Claim", "source_refs": [{"source_id": "s1"}]}]},
    "check_unsupported_claims": {"claims": [{"claim_id": "c1", "text": "Claim", "source_refs": [{"source_id": "s1"}]}]},
    "check_recommendation_language": {"text": "Review the downside before acting."},
    "check_stale_data": {
        "now": "2026-06-30T00:00:00+00:00",
        "items": [{"source_id": "s1", "as_of": "2026-06-30T00:00:00+00:00"}],
    },
    "assess_rag_confidence": {"query": "risk", "contexts": [{"text": "risk first", "score": 0.9}]},
    "quality_score": {"checks": [{"status": "passed"}]},
    "generate_stock_snapshot": {"ticker": "AAPL", "price_data": {"price": 200}},
    "generate_portfolio_report": {"holdings": [{"ticker": "AAPL", "weight": 1}]},
    "generate_daily_check": {"market_brief": "Market mixed.", "portfolio_summary": "No changes."},
    "generate_weekly_review": {"journal_entries": [{"ticker": "AAPL", "action": "buy"}]},
    "format_persona_output": {"text": "Check risk and source data.", "persona": "risk"},
    "fetch_news": {"news": [{"title": "AAPL update", "ticker": "AAPL", "as_of": "2026-06-30T00:00:00+00:00"}]},
    "fetch_filings": {"filings": [{"title": "10-Q", "ticker": "AAPL", "as_of": "2026-06-30T00:00:00+00:00"}]},
    "fetch_financials": {"ticker": "AAPL", "financials": {"revenue": 1, "as_of": "2026-06-30T00:00:00+00:00"}},
    "load_journal_entries": {"journal_entries": [{"ticker": "AAPL", "action": "buy"}]},
    "load_current_holdings": {"holdings": [{"ticker": "AAPL", "quantity": 1, "market_price": 100, "cost_basis": 90}]},
    "fetch_market_indices": {"indices": [{"name": "S&P 500", "value": 5500, "as_of": "2026-06-30T00:00:00+00:00"}]},
    "fetch_macro_indicators": {"macro_indicators": [{"name": "VIX", "value": 15, "as_of": "2026-06-30T00:00:00+00:00"}]},
    "analyze_sector_rotation": {"sectors": [{"sector": "Technology", "return": 0.02}, {"sector": "Utilities", "return": -0.01}]},
    "detect_risk_on_off": {"signals": {"equity_return": 0.02, "vix": 15, "credit_spread": -0.1}},
    "generate_market_brief": {"regime": {"regime": "risk_on"}, "indices": [{"name": "S&P 500", "value": 5500}]},
}


def catalog_skills_from_spec() -> set[str]:
    spec = Path("docs/spec/03-skills-catalog.md").read_text(encoding="utf-8")
    headings = [
        "RAG Skills",
        "Portfolio Skills",
        "Knowledge Skills",
        "Verification Skills",
        "Report Skills",
        "Data Skills",
        "Market Regime Skills",
    ]
    skills: set[str] = set()
    for heading in headings:
        match = re.search(rf"## {re.escape(heading)}\n(?P<section>.*?)(?=\n## |\Z)", spec, flags=re.DOTALL)
        if match:
            skills.update(re.findall(r"^\|\s*`([^`]+)`\s*\|", match.group("section"), flags=re.MULTILINE))
    return skills


class SkillCatalogTests(TestCase):
    def test_catalog_registry_contains_all_spec_skills(self):
        self.assertEqual(set(list_skills()), catalog_skills_from_spec())

    def test_all_catalog_skills_return_skill_output_envelopes(self):
        self.assertEqual(set(SKILL_CASES), catalog_skills_from_spec())
        for skill_name, options in SKILL_CASES.items():
            with self.subTest(skill_name=skill_name):
                output = invoke_skill(skill_name, SkillInput(run_id=f"run_{skill_name}", options=options))
                self.assertIn(output.status, {SkillStatus.SUCCESS, SkillStatus.PARTIAL})
                self.assertIsInstance(output.data, dict)
                self.assertIsInstance(output.model_dump_json(), str)

    def test_side_effect_classes_match_catalog_contract(self):
        effect_cases = {
            "calculate_returns": ({"holdings": [{"ticker": "AAPL", "cost_basis": 100, "market_price": 110}]}, SkillEffect.PURE),
            "calculate_weights": ({"holdings": [{"ticker": "AAPL", "quantity": 1, "market_price": 100}]}, SkillEffect.PURE),
            "fetch_news": ({"news": [{"title": "AAPL update", "as_of": "2026-06-30T00:00:00+00:00"}]}, SkillEffect.READ_EXTERNAL),
            "fetch_price_data": ({"prices": [{"ticker": "AAPL", "price": 200, "as_of": "2026-06-30T00:00:00+00:00"}]}, SkillEffect.READ_EXTERNAL),
            "create_wiki_revision": ({"proposed_body": "Always define risk.", "page_id": "page_1"}, SkillEffect.PROPOSE_REVISION),
            "embed_chunks": ({"chunks": [{"chunk_id": "chunk_1", "document_id": "doc_1", "text": "risk first"}], "dimensions": 8}, SkillEffect.WRITE_INTERNAL),
        }

        for skill_name, (options, expected_effect) in effect_cases.items():
            with self.subTest(skill_name=skill_name):
                output = invoke_skill(skill_name, SkillInput(run_id=f"run_{skill_name}", options=options))
                self.assertEqual(output.effect, expected_effect)

    def test_rag_pipeline_skills_run_through_langgraph(self):
        parsed = invoke_skill(
            "parse_document",
            SkillInput(run_id="run_test", options={"text": "Always define risk before entry.", "title": "Memo"}),
        )
        self.assertEqual(parsed.status, SkillStatus.SUCCESS)

        chunked = invoke_skill(
            "chunk_document",
            SkillInput(run_id="run_test", options={"text": parsed.data["text"], "chunk_size": 50, "overlap": 0}),
        )
        self.assertEqual(chunked.status, SkillStatus.SUCCESS)
        self.assertGreaterEqual(chunked.data["chunk_count"], 1)

        embedded = invoke_skill(
            "embed_chunks",
            SkillInput(run_id="run_test", options={"chunks": chunked.data["chunks"], "dimensions": 8}),
        )
        self.assertEqual(embedded.status, SkillStatus.PARTIAL)
        self.assertEqual(embedded.data["embedding_count"], chunked.data["chunk_count"])
        self.assertEqual(embedded.data["write_log"]["target_tables"], ["source_documents", "chunks"])
        self.assertIn("rollback", embedded.data["write_log"])

    def test_parse_document_reads_text_files_and_pdf_pages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            text_path = Path(tmpdir) / "memo.txt"
            text_path.write_text("Always define risk before entry.", encoding="utf-8")
            text_output = invoke_skill(
                "parse_document",
                SkillInput(run_id="run_text_file", options={"file_path": str(text_path), "title": "Memo"}),
            )

        self.assertEqual(text_output.status, SkillStatus.SUCCESS)
        self.assertEqual(text_output.effect, SkillEffect.READ_EXTERNAL)
        self.assertEqual(text_output.data["parser"], "text_file")
        self.assertIn("Always define risk", text_output.data["text"])

        class FakePage:
            def __init__(self, text):
                self.text = text

            def extract_text(self):
                return self.text

        class FakeReader:
            pages = [FakePage("Risk first."), FakePage("Size second.")]
            metadata = {"/Title": "Fake PDF"}

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "memo.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")
            with patch("pypdf.PdfReader", return_value=FakeReader()):
                pdf_output = invoke_skill(
                    "parse_document",
                    SkillInput(run_id="run_pdf_file", options={"file_path": str(pdf_path), "title": "PDF Memo"}),
                )

        self.assertEqual(pdf_output.status, SkillStatus.SUCCESS)
        self.assertEqual(pdf_output.effect, SkillEffect.READ_EXTERNAL)
        self.assertEqual(pdf_output.data["parser"], "pypdf")
        self.assertEqual(pdf_output.data["metadata"]["page_count"], 2)
        self.assertIn("Risk first.", pdf_output.data["text"])

    def test_portfolio_calculation_skills_return_weights_and_flags(self):
        weights = invoke_skill(
            "calculate_weights",
            SkillInput(
                run_id="run_test",
                options={
                    "cash": 100,
                    "holdings": [
                        {"ticker": "aapl", "quantity": 10, "market_price": 20, "sector": "Technology"},
                        {"ticker": "msft", "quantity": 5, "market_price": 20, "sector": "Technology"},
                    ],
                },
            ),
        )
        self.assertEqual(weights.status, SkillStatus.SUCCESS)
        self.assertAlmostEqual(weights.data["total_value"], 400.0)

        concentration = invoke_skill(
            "detect_concentration",
            SkillInput(run_id="run_test", options={"holdings": weights.data["holdings"], "sector_threshold": 0.5}),
        )
        self.assertEqual(concentration.status, SkillStatus.SUCCESS)
        self.assertTrue(concentration.data["is_concentrated"])

    def test_verification_skills_detect_missing_citations_and_forbidden_language(self):
        citations = invoke_skill(
            "verify_citations",
            SkillInput(run_id="run_test", options={"claims": [{"claim_id": "claim_1", "text": "AAPL is strong."}]}),
        )
        self.assertEqual(citations.status, SkillStatus.SUCCESS)
        self.assertEqual(citations.data["status"], "needs_human_review")

        language = invoke_skill(
            "check_recommendation_language",
            SkillInput(run_id="run_test", options={"text": "Buy now because returns are guaranteed."}),
        )
        self.assertEqual(language.status, SkillStatus.SUCCESS)
        self.assertEqual(language.data["status"], "blocked")

    def test_formatter_rechecks_prohibited_language_after_persona_formatting(self):
        output = invoke_skill(
            "format_persona_output",
            SkillInput(run_id="run_test", options={"text": "Buy now because returns are guaranteed.", "persona": "coach"}),
        )

        self.assertEqual(output.status, SkillStatus.BLOCKED)
        self.assertIn("language_checks", output.error.details)

    def test_create_wiki_revision_can_persist_as_draft_without_accepting_page(self):
        persisted = {
            "page_id": "page_1",
            "page_row_id": "page-row-uuid",
            "revision_id": "rev_1",
            "revision_row_id": "revision-row-uuid",
        }
        with (
            patch("invest_llm_agents.skills.knowledge.resolve_database_url", return_value="postgresql://example/db"),
            patch("invest_llm_agents.skills.knowledge.upsert_wiki_revision", return_value=persisted) as upsert,
        ):
            output = invoke_skill(
                "create_wiki_revision",
                SkillInput(
                    run_id="run_test",
                    options={
                        "revision_id": "rev_1",
                        "page_id": "page_1",
                        "proposed_body": "Always define risk.",
                        "persist": True,
                    },
                ),
            )

        self.assertEqual(output.status, SkillStatus.SUCCESS)
        self.assertEqual(output.data["persistence"], persisted)
        self.assertEqual(output.data["revision"]["status"], "draft")
        self.assertEqual(output.data["page"]["body"], "")
        self.assertEqual(output.data["write_log"]["target_tables"], ["wiki_pages", "wiki_revisions"])
        upsert.assert_called_once()

    def test_report_skills_can_persist_report_drafts_when_requested(self):
        persisted = {"report_id": "report_1", "report_row_id": "report-row-uuid"}
        with (
            patch("invest_llm_agents.skills.reports.resolve_database_url", return_value="postgresql://example/db"),
            patch("invest_llm_agents.skills.reports.upsert_report_draft", return_value=persisted) as upsert,
        ):
            output = invoke_skill(
                "generate_daily_check",
                SkillInput(
                    run_id="run_test",
                    options={
                        "report_id": "report_1",
                        "market_brief": "Market mixed.",
                        "portfolio_summary": "No changes.",
                        "persist": True,
                    },
                ),
            )

        self.assertEqual(output.status, SkillStatus.SUCCESS)
        self.assertEqual(output.effect, SkillEffect.WRITE_INTERNAL)
        self.assertEqual(output.data["persistence"], persisted)
        self.assertEqual(output.data["report"]["verification_status"], "pending")
        self.assertEqual(output.data["write_log"]["target_tables"], ["report_drafts"])
        upsert.assert_called_once()

    def test_persistence_failures_keep_named_error_codes_and_effects(self):
        with (
            patch("invest_llm_agents.skills.rag.resolve_database_url", return_value="postgresql://example/db"),
            patch("invest_llm_agents.skills.rag.upsert_document_and_chunks", side_effect=TimeoutError("db timeout")),
        ):
            embedded = invoke_skill(
                "embed_chunks",
                SkillInput(
                    run_id="run_test",
                    options={
                        "persist": True,
                        "chunks": [{"chunk_id": "chunk_1", "document_id": "doc_1", "text": "risk first"}],
                        "dimensions": 8,
                    },
                ),
            )

        self.assertEqual(embedded.status, SkillStatus.BLOCKED)
        self.assertEqual(embedded.effect, SkillEffect.WRITE_INTERNAL)
        self.assertEqual(embedded.error.error_code, "PARTIAL_EXTERNAL_OUTAGE")
        self.assertEqual(embedded.data["storage_status"], "persistence_failed")

        with (
            patch("invest_llm_agents.skills.rag.resolve_database_url", return_value="postgresql://example/db"),
            patch("invest_llm_agents.skills.rag.search_chunks", side_effect=TimeoutError("db timeout")),
        ):
            retrieved = invoke_skill(
                "retrieve_related_chunks",
                SkillInput(run_id="run_test", options={"query": "risk"}),
            )

        self.assertEqual(retrieved.status, SkillStatus.NEEDS_HUMAN_REVIEW)
        self.assertEqual(retrieved.effect, SkillEffect.READ_EXTERNAL)
        self.assertEqual(retrieved.error.error_code, "PARTIAL_EXTERNAL_OUTAGE")
