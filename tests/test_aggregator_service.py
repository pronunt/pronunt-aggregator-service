import asyncio
from datetime import UTC, datetime, timedelta

from bson import ObjectId
from fastapi import Request

from app.core.auth import AuthContext
from app.core.settings import Settings
from app.schemas.pull_request import (
    AggregatorSummaryResponse,
    ImpactDetail,
    PullRequestFilters,
    PullRequestSortField,
    PullRequestUpsertRequest,
    ReviewStatus,
    ServiceCriticality,
    SortDirection,
)
from app.schemas.ai import AiProviderOverride
from app.services.aggregator import AggregatorService, ResolvedPullRequestMetadata, Scorecard


class FakePullRequestRepository:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}

    def upsert(self, payload: PullRequestUpsertRequest, scorecard: Scorecard) -> dict:
        existing_id = next((doc_id for doc_id, document in self.documents.items() if document["pr_uid"] == f"{payload.repository_full_name}#{payload.number}"), None)
        document_id = existing_id or str(ObjectId())
        document = {
            "_id": ObjectId(document_id),
            "pr_uid": f"{payload.repository_full_name}#{payload.number}",
            **payload.model_dump(),
            "risk_score": scorecard.risk_score,
            "priority_score": scorecard.priority_score,
            "stale": scorecard.stale,
            "stale_hours": scorecard.stale_hours,
            "impact_services": scorecard.impact_services,
            "score_breakdown": scorecard.score_breakdown,
            "synced_at": datetime.now(UTC),
            "last_scored_at": datetime.now(UTC),
        }
        self.documents[document_id] = document
        return document

    def get_by_id(self, pr_id: str) -> dict | None:
        return self.documents.get(pr_id)

    def list(self, filters: PullRequestFilters, sort_by: PullRequestSortField, sort_direction: SortDirection, limit: int, offset: int) -> tuple[list[dict], int]:
        items = list(self.documents.values())
        if filters.stale is not None:
            items = [item for item in items if item["stale"] == filters.stale]
        items.sort(key=lambda item: item[sort_by.value], reverse=sort_direction == SortDirection.desc)
        total = len(items)
        return items[offset : offset + limit], total

    def recompute_scores(self, pr_id: str, scorecard: Scorecard) -> dict | None:
        document = self.documents.get(pr_id)
        if not document:
            return None
        document.update(
            {
                "risk_score": scorecard.risk_score,
                "priority_score": scorecard.priority_score,
                "stale": scorecard.stale,
                "stale_hours": scorecard.stale_hours,
                "impact_services": scorecard.impact_services,
                "score_breakdown": scorecard.score_breakdown,
                "last_scored_at": datetime.now(UTC),
            }
        )
        return document

    def update_ai_summary(self, pr_id: str, summary: str) -> dict | None:
        document = self.documents.get(pr_id)
        if not document:
            return None
        document["ai_summary"] = summary
        document["synced_at"] = datetime.now(UTC)
        return document

    def summary(self) -> AggregatorSummaryResponse:
        items = list(self.documents.values())
        return AggregatorSummaryResponse(
            total_open=sum(1 for item in items if item["state"] == "open"),
            total_stale=sum(1 for item in items if item["state"] == "open" and item["stale"]),
            total_high_risk=sum(1 for item in items if item["state"] == "open" and item["risk_score"] >= 70),
            total_high_priority=sum(1 for item in items if item["state"] == "open" and item["priority_score"] >= 70),
            by_criticality={
                "low": sum(1 for item in items if item["state"] == "open" and item["criticality"] == ServiceCriticality.low),
                "medium": sum(1 for item in items if item["state"] == "open" and item["criticality"] == ServiceCriticality.medium),
                "high": sum(1 for item in items if item["state"] == "open" and item["criticality"] == ServiceCriticality.high),
                "critical": sum(1 for item in items if item["state"] == "open" and item["criticality"] == ServiceCriticality.critical),
            },
        )


class FakeConfigResolver:
    def __init__(self, criticality: ServiceCriticality = ServiceCriticality.high, impact_services: list[str] | None = None) -> None:
        self.criticality = criticality
        self.impact_services = impact_services or ["pronunt-config-service", "pronunt-ai-service"]

    async def resolve_pull_request_metadata(self, payload, request, auth_context) -> ResolvedPullRequestMetadata:
        return ResolvedPullRequestMetadata(
            criticality=self.criticality,
            impact_services=self.impact_services,
            impact_summary="Impact summary for test payload.",
            impact_details=[
                ImpactDetail(
                    service_name=service_name,
                    relationship="downstream",
                    path=["pronunt-aggregator-service", service_name],
                    explanation=f"{service_name} is impacted in the test graph.",
                )
                for service_name in self.impact_services
            ],
        )


class FakeAiSummaryResolver:
    async def summarize_pull_request(self, pull_request, request, auth_context, provider_override=None):
        from app.schemas.ai import AiSummaryResponse

        model = provider_override.model if provider_override is not None and provider_override.model else "test-model"
        return AiSummaryResponse(
            summary=f"Summary for {pull_request.pr_uid}",
            generated_by="fake",
            model=model,
        )


def _build_payload(
    number: int = 1,
    hours_ago: int = 10,
    criticality: ServiceCriticality = ServiceCriticality.high,
) -> PullRequestUpsertRequest:
    now = datetime.now(UTC)
    return PullRequestUpsertRequest(
        repository_full_name="pronunt/pronunt-aggregator-service",
        repository_owner="pronunt",
        repository_name="pronunt-aggregator-service",
        number=number,
        title="Add persisted aggregator flow",
        author_username="sowrabh0-0",
        state="open",
        review_status=ReviewStatus.pending,
        is_draft=False,
        html_url=f"https://github.com/pronunt/pronunt-aggregator-service/pull/{number}",
        base_branch="main",
        head_branch="feat/setup-gitops-workflows",
        labels=["backend", "aggregator"],
        changed_files=18,
        additions=340,
        deletions=90,
        criticality=criticality,
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(hours=hours_ago),
        impact_services=["pronunt-config-service", "pronunt-ai-service"],
    )


def test_upsert_assigns_scores_and_persists_document() -> None:
    service = AggregatorService(
        FakePullRequestRepository(),
        Settings(_env_file=None, allow_unsafe_dev_auth=True),
        FakeConfigResolver(),
        FakeAiSummaryResolver(),
    )
    request = Request({"type": "http", "headers": [], "state": {}})
    auth_context = AuthContext(subject="dev-user", username="dev-user", roles=["developer"], token="token")

    response = asyncio.run(service.upsert_pull_request(_build_payload(hours_ago=6), request, auth_context))

    assert response.repository_name == "pronunt-aggregator-service"
    assert response.risk_score > 0
    assert response.priority_score > 0
    assert response.stale is False


def test_stale_pull_request_gets_marked_and_prioritized() -> None:
    service = AggregatorService(
        FakePullRequestRepository(),
        Settings(_env_file=None, allow_unsafe_dev_auth=True, aggregator_stale_after_hours=48),
        FakeConfigResolver(criticality=ServiceCriticality.critical),
        FakeAiSummaryResolver(),
    )
    request = Request({"type": "http", "headers": [], "state": {}})
    auth_context = AuthContext(subject="dev-user", username="dev-user", roles=["developer"], token="token")

    response = asyncio.run(service.upsert_pull_request(_build_payload(hours_ago=96), request, auth_context))

    assert response.stale is True
    assert response.stale_hours >= 96
    assert response.priority_score >= 70


def test_list_and_summary_reflect_persisted_pull_requests() -> None:
    repository = FakePullRequestRepository()
    service = AggregatorService(
        repository,
        Settings(_env_file=None, allow_unsafe_dev_auth=True),
        FakeConfigResolver(),
        FakeAiSummaryResolver(),
    )
    request = Request({"type": "http", "headers": [], "state": {}})
    auth_context = AuthContext(subject="dev-user", username="dev-user", roles=["developer"], token="token")
    asyncio.run(service.upsert_pull_request(_build_payload(number=1, hours_ago=96), request, auth_context))
    asyncio.run(service.upsert_pull_request(_build_payload(number=2, hours_ago=8), request, auth_context))

    listing = service.list_pull_requests(PullRequestFilters(), PullRequestSortField.priority_score, SortDirection.desc, 25, 0)
    summary = service.get_summary()

    assert listing.total == 2
    assert len(listing.items) == 2
    assert summary.total_open == 2


def test_config_metadata_overrides_incoming_payload_values() -> None:
    service = AggregatorService(
        FakePullRequestRepository(),
        Settings(_env_file=None, allow_unsafe_dev_auth=True),
        FakeConfigResolver(
            criticality=ServiceCriticality.critical,
            impact_services=["pronunt-worker-service", "pronunt-frontend-service"],
        ),
        FakeAiSummaryResolver(),
    )
    request = Request({"type": "http", "headers": [], "state": {}})
    auth_context = AuthContext(subject="dev-user", username="dev-user", roles=["developer"], token="token")
    payload = _build_payload(number=3, hours_ago=6, criticality=ServiceCriticality.low)

    response = asyncio.run(service.upsert_pull_request(payload, request, auth_context))

    assert response.criticality == ServiceCriticality.critical
    assert response.impact_services == ["pronunt-frontend-service", "pronunt-worker-service"]
    assert response.impact_summary == "Impact summary for test payload."
    assert len(response.impact_details) == 2


def test_generate_pull_request_summary_persists_summary() -> None:
    repository = FakePullRequestRepository()
    service = AggregatorService(
        repository,
        Settings(_env_file=None, allow_unsafe_dev_auth=True),
        FakeConfigResolver(),
        FakeAiSummaryResolver(),
    )
    request = Request({"type": "http", "headers": [], "state": {}})
    auth_context = AuthContext(subject="dev-user", username="dev-user", roles=["developer"], token="token")
    created = asyncio.run(service.upsert_pull_request(_build_payload(number=5, hours_ago=4), request, auth_context))

    summary = asyncio.run(service.generate_pull_request_summary(created.id, request, auth_context))
    stored = service.get_pull_request(created.id)

    assert summary.generated_by == "fake"
    assert "Summary for" in summary.ai_summary
    assert stored.ai_summary == summary.ai_summary


def test_generate_pull_request_summary_accepts_provider_override() -> None:
    repository = FakePullRequestRepository()
    service = AggregatorService(
        repository,
        Settings(_env_file=None, allow_unsafe_dev_auth=True),
        FakeConfigResolver(),
        FakeAiSummaryResolver(),
    )
    request = Request({"type": "http", "headers": [], "state": {}})
    auth_context = AuthContext(subject="dev-user", username="dev-user", roles=["developer"], token="token")
    created = asyncio.run(service.upsert_pull_request(_build_payload(number=6, hours_ago=2), request, auth_context))

    summary = asyncio.run(
        service.generate_pull_request_summary(
            created.id,
            request,
            auth_context,
            provider_override=AiProviderOverride(provider="openai", model="gpt-4.1-mini"),
        )
    )

    assert summary.model == "gpt-4.1-mini"
