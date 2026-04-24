from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.pull_request import PullRequestUpsertRequest
    from app.services.aggregator import Scorecard


def utc_now() -> datetime:
    return datetime.now(UTC)


def build_pr_uid(repository_full_name: str, number: int) -> str:
    return f"{repository_full_name}#{number}"


def build_pull_request_document(payload: PullRequestUpsertRequest, scorecard: Scorecard) -> dict[str, object]:
    now = utc_now()
    return {
        "pr_uid": build_pr_uid(payload.repository_full_name, payload.number),
        "repository_full_name": payload.repository_full_name,
        "repository_owner": payload.repository_owner,
        "repository_name": payload.repository_name,
        "number": payload.number,
        "title": payload.title,
        "author_username": payload.author_username,
        "state": payload.state,
        "review_status": payload.review_status,
        "is_draft": payload.is_draft,
        "html_url": payload.html_url,
        "base_branch": payload.base_branch,
        "head_branch": payload.head_branch,
        "labels": payload.labels,
        "changed_files": payload.changed_files,
        "additions": payload.additions,
        "deletions": payload.deletions,
        "criticality": payload.criticality,
        "created_at": payload.created_at,
        "updated_at": payload.updated_at,
        "merged_at": payload.merged_at,
        "closed_at": payload.closed_at,
        "ai_summary": payload.ai_summary,
        "risk_score": scorecard.risk_score,
        "priority_score": scorecard.priority_score,
        "stale": scorecard.stale,
        "stale_hours": scorecard.stale_hours,
        "impact_services": scorecard.impact_services,
        "score_breakdown": scorecard.score_breakdown,
        "synced_at": now,
        "last_scored_at": now,
    }
