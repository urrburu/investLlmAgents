"""Markdown renderers for the MVP user-facing surfaces."""

from invest_llm_agents.common.enums import VerificationStatus
from invest_llm_agents.common.models import ReportDraft, VerificationResult, WikiRevision
from invest_llm_agents.common.verification import RescuePayload, report_can_be_promoted


def render_rescue(payload: RescuePayload) -> str:
    lines = [
        "# 검토가 필요한 결과입니다",
        "",
        f"상태: {payload.verification_status}",
        f"오류 코드: {payload.error_code}",
        "",
        "## 막힌 이유",
        "",
        payload.message,
    ]

    if payload.blocked_reasons:
        lines.extend(["", "## 세부 사유", ""])
        lines.extend(f"- {reason}" for reason in payload.blocked_reasons)

    lines.extend(["", "## 안전하게 보여줄 수 있는 섹션", ""])
    lines.extend(f"- {section}" for section in payload.safe_sections) if payload.safe_sections else lines.append("없음")

    lines.extend(["", "## 숨긴 섹션", ""])
    lines.extend(f"- {section}" for section in payload.hidden_sections) if payload.hidden_sections else lines.append("없음")

    lines.extend(["", "## 필요한 입력", ""])
    lines.extend(f"- {item}" for item in payload.required_inputs) if payload.required_inputs else lines.append("없음")

    return "\n".join(lines)


def render_report_or_rescue(report: ReportDraft, verification: VerificationResult) -> str:
    if not report_can_be_promoted(report, verification):
        payload = RescuePayload(
            verification_status=verification.status,
            error_code="LOW_RAG_CONFIDENCE",
            message="검증 상태가 passed가 아니어서 최종 리포트로 승격하지 않았습니다.",
            blocked_reasons=verification.required_fixes,
            required_inputs=verification.required_inputs,
            safe_sections=verification.safe_sections,
            hidden_sections=verification.hidden_sections,
        )
        return render_rescue(payload)

    lines = [
        f"# {report.title}",
        "",
        f"검증 상태: {report.verification_status}",
    ]
    if report.as_of is not None:
        lines.append(f"기준일: {report.as_of.isoformat()}")

    source_labels = [ref.citation_label or ref.source_id for ref in report.source_refs]
    if source_labels:
        lines.append(f"출처: {', '.join(source_labels)}")

    visible_sections = sorted(
        (section for section in report.sections if section.status == VerificationStatus.PASSED),
        key=lambda section: section.display_order,
    )
    for section in visible_sections:
        lines.extend(["", f"## {section.title}", "", section.body or "(내용 없음)"])

    return "\n".join(lines)


def render_revision_review(revision: WikiRevision, verification: VerificationResult | None = None) -> str:
    lines = [
        "# 위키 Revision 검토",
        "",
        f"revision_id: {revision.revision_id}",
        f"page_id: {revision.page_id}",
        f"operation: {revision.operation}",
        f"status: {revision.status}",
        "",
        "## 변경 요약",
        "",
        revision.change_summary,
        "",
        "## Before / After",
        "",
        revision.diff_summary,
        "",
        "## 근거",
        "",
    ]
    lines.extend(f"- {ref.citation_label or ref.source_id}" for ref in revision.source_refs) if revision.source_refs else lines.append("- 근거 없음")

    if verification is not None:
        lines.extend(
            [
                "",
                "## 검증 결과",
                "",
                f"- 상태: {verification.status}",
                f"- 품질 점수: {verification.quality_score}",
            ]
        )

    lines.extend(
        [
            "",
            "## 가능한 행동",
            "",
            "- approve: 현재 위키에 반영",
            "- reject: 폐기하고 사유 기록",
            "- request_changes: 수정 요청을 남기고 재생성",
        ]
    )
    return "\n".join(lines)

