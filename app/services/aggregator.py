from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Protocol

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, Request, status
from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection

from app.core.auth import AuthContext
from app.core.database import get_pull_request_collection
from app.core.exceptions import AppException
from app.core.http import service_request
from app.core.settings import Settings, get_settings
from app.models.pull_request import build_pull_request_document
from app.schemas.ai import AiSummaryRequest, AiSummaryResponse
from app.schemas.config import ConfigImpactResponse, ConfigServiceResponse
from app.schemas.pull_request import (
    AggregatorSummaryResponse,
    PullRequestFilters,
    PullRequestListResponse,
    PullRequestResponse,
    PullRequestSortField,
    PullRequestUpsertRequest,
    PullRequestSummaryResponse,
    ReviewStatus,
    ServiceCriticality,
    SortDirection,
)

OPEN_PULL_REQUEST_STATE = "open"
PULL_REQUEST_NOT_FOUND_CODE = "pull_request_not_found"
PULL_REQUEST_NOT_FOUND_MESSAGE = "Pull request was not found."


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _hours_since(updated_at: datetime) -> int:
    now = _utc_now()
    normalized = updated_at.astimezone(UTC) if updated_at.tzinfo else updated_at.replace(tzinfo=UTC)
    return max(0, int((now - normalized).total_seconds() // 3600))


def _clamp(value: int, minimum: int = 0, maximum: int = 100) -> int:
    return max(minimum, min(maximum, value))


def _score_size(changed_files: int) -> int:
    if changed_files >= 40:
        return 35
    if changed_files >= 20:
        return 25
    if changed_files >= 10:
        return 15
    if changed_files >= 5:
        return 8
    return 3


def _score_churn(additions: int, deletions: int) -> int:
    churn = additions + deletions
    if churn >= 1200:
        return 30
    if churn >= 600:
        return 22
    if churn >= 250:
        return 14
    if churn >= 100:
        return 8
    return 3


def _score_criticality(criticality: ServiceCriticality) -> int:
    return {
        ServiceCriticality.low: 5,
        ServiceCriticality.medium: 12,
        ServiceCriticality.high: 20,
        ServiceCriticality.critical: 30,
    }[criticality]


def _score_review_status(review_status: ReviewStatus) -> int:
    return {
        ReviewStatus.pending: 18,
        ReviewStatus.commented: 12,
        ReviewStatus.changes_requested: 16,
        ReviewStatus.approved: 4,
    }[review_status]


@dataclass
class Scorecard:
    risk_score: int
    priority_score: int
    stale: bool
    stale_hours: int
    impact_services: list[str]
    score_breakdown: dict[str, int]


@dataclass
class ResolvedPullRequestMetadata:
    criticality: ServiceCriticality
    impact_services: list[str]


class PullRequestRepository(Protocol):
    def upsert(self, payload: PullRequestUpsertRequest, scorecard: Scorecard) -> dict: ...

    def get_by_id(self, pr_id: str) -> dict | None: ...

    def list(self, filters: PullRequestFilters, sort_by: PullRequestSortField, sort_direction: SortDirection, limit: int, offset: int) -> tuple[list[dict], int]: ...

    def recompute_scores(self, pr_id: str, scorecard: Scorecard) -> dict | None: ...

    def update_ai_summary(self, pr_id: str, summary: str) -> dict | None: ...

    def summary(self) -> AggregatorSummaryResponse: ...


class ConfigResolver(Protocol):
    async def resolve_pull_request_metadata(
        self,
        payload: PullRequestUpsertRequest,
        request: Request,
        auth_context: AuthContext,
    ) -> ResolvedPullRequestMetadata: ...


class AiSummaryResolver(Protocol):
    async def summarize_pull_request(
        self,
        pull_request: PullRequestResponse,
        request: Request,
        auth_context: AuthContext,
    ) -> AiSummaryResponse: ...


class MongoPullRequestRepository:
    def __init__(self, collection: Collection) -> None:
        self.collection = collection
        self.collection.create_index("pr_uid", unique=True)
        self.collection.create_index([("state", ASCENDING), ("priority_score", DESCENDING)])

    def upsert(self, payload: PullRequestUpsertRequest, scorecard: Scorecard) -> dict:
        document = build_pull_request_document(payload, scorecard)
        self.collection.update_one(
            {"pr_uid": document["pr_uid"]},
            {"$set": document},
            upsert=True,
        )
        return self.collection.find_one({"pr_uid": document["pr_uid"]})

    def get_by_id(self, pr_id: str) -> dict | None:
        try:
            return self.collection.find_one({"_id": ObjectId(pr_id)})
        except InvalidId:
            return None

    def list(
        self,
        filters: PullRequestFilters,
        sort_by: PullRequestSortField,
        sort_direction: SortDirection,
        limit: int,
        offset: int,
    ) -> tuple[list[dict], int]:
        query: dict = {}
        if filters.repository_full_name:
            query["repository_full_name"] = filters.repository_full_name
        if filters.author_username:
            query["author_username"] = filters.author_username
        if filters.state:
            query["state"] = filters.state.value
        if filters.review_status:
            query["review_status"] = filters.review_status.value
        if filters.stale is not None:
            query["stale"] = filters.stale
        if filters.min_risk_score is not None:
            query["risk_score"] = {"$gte": filters.min_risk_score}
        if filters.min_priority_score is not None:
            query["priority_score"] = {"$gte": filters.min_priority_score}

        direction = DESCENDING if sort_direction == SortDirection.desc else ASCENDING
        cursor = self.collection.find(query).sort(sort_by.value, direction).skip(offset).limit(limit)
        return list(cursor), self.collection.count_documents(query)

    def recompute_scores(self, pr_id: str, scorecard: Scorecard) -> dict | None:
        try:
            object_id = ObjectId(pr_id)
        except InvalidId:
            return None

        update = {
            "$set": {
                "risk_score": scorecard.risk_score,
                "priority_score": scorecard.priority_score,
                "stale": scorecard.stale,
                "stale_hours": scorecard.stale_hours,
                "impact_services": scorecard.impact_services,
                "score_breakdown": scorecard.score_breakdown,
                "last_scored_at": _utc_now(),
            }
        }
        self.collection.update_one({"_id": object_id}, update)
        return self.collection.find_one({"_id": object_id})

    def update_ai_summary(self, pr_id: str, summary: str) -> dict | None:
        try:
            object_id = ObjectId(pr_id)
        except InvalidId:
            return None

        self.collection.update_one(
            {"_id": object_id},
            {"$set": {"ai_summary": summary, "synced_at": _utc_now()}},
        )
        return self.collection.find_one({"_id": object_id})

    def summary(self) -> AggregatorSummaryResponse:
        return AggregatorSummaryResponse(
            total_open=self.collection.count_documents({"state": OPEN_PULL_REQUEST_STATE}),
            total_stale=self.collection.count_documents({"state": OPEN_PULL_REQUEST_STATE, "stale": True}),
            total_high_risk=self.collection.count_documents({"state": OPEN_PULL_REQUEST_STATE, "risk_score": {"$gte": 70}}),
            total_high_priority=self.collection.count_documents({"state": OPEN_PULL_REQUEST_STATE, "priority_score": {"$gte": 70}}),
            by_criticality={
                "low": self.collection.count_documents({"state": OPEN_PULL_REQUEST_STATE, "criticality": "low"}),
                "medium": self.collection.count_documents({"state": OPEN_PULL_REQUEST_STATE, "criticality": "medium"}),
                "high": self.collection.count_documents({"state": OPEN_PULL_REQUEST_STATE, "criticality": "high"}),
                "critical": self.collection.count_documents({"state": OPEN_PULL_REQUEST_STATE, "criticality": "critical"}),
            },
        )


class AggregatorService:
    def __init__(
        self,
        repository: PullRequestRepository,
        settings: Settings,
        config_resolver: ConfigResolver,
        ai_summary_resolver: AiSummaryResolver,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.config_resolver = config_resolver
        self.ai_summary_resolver = ai_summary_resolver

    async def upsert_pull_request(
        self,
        payload: PullRequestUpsertRequest,
        request: Request,
        auth_context: AuthContext,
    ) -> PullRequestResponse:
        resolved_payload = await self._build_resolved_payload(payload, request, auth_context)
        scorecard = self._build_scorecard(resolved_payload)
        document = self.repository.upsert(resolved_payload, scorecard)
        return self._to_response(document)

    def get_pull_request(self, pr_id: str) -> PullRequestResponse:
        document = self.repository.get_by_id(pr_id)
        if not document:
            self._raise_not_found(pr_id)
        return self._to_response(document)

    def list_pull_requests(
        self,
        filters: PullRequestFilters,
        sort_by: PullRequestSortField,
        sort_direction: SortDirection,
        limit: int,
        offset: int,
    ) -> PullRequestListResponse:
        documents, total = self.repository.list(filters, sort_by, sort_direction, limit, offset)
        return PullRequestListResponse(items=[self._to_response(document) for document in documents], total=total)

    async def recompute_pull_request_scores(
        self,
        pr_id: str,
        request: Request,
        auth_context: AuthContext,
    ) -> PullRequestResponse:
        current = self.repository.get_by_id(pr_id)
        if not current:
            self._raise_not_found(pr_id)

        payload = self._build_payload_from_document(current)
        resolved_payload = await self._build_resolved_payload(payload, request, auth_context)
        document = self.repository.recompute_scores(pr_id, self._build_scorecard(resolved_payload))
        if not document:
            self._raise_not_found(pr_id)
        return self._to_response(document)

    def get_summary(self) -> AggregatorSummaryResponse:
        return self.repository.summary()

    async def generate_pull_request_summary(
        self,
        pr_id: str,
        request: Request,
        auth_context: AuthContext,
    ) -> PullRequestSummaryResponse:
        current = self.repository.get_by_id(pr_id)
        if not current:
            self._raise_not_found(pr_id)

        pull_request = self._to_response(current)
        ai_summary = await self.ai_summary_resolver.summarize_pull_request(pull_request, request, auth_context)
        updated = self.repository.update_ai_summary(pr_id, ai_summary.summary)
        if not updated:
            self._raise_not_found(pr_id)

        return PullRequestSummaryResponse(
            id=str(updated["_id"]),
            pr_uid=updated["pr_uid"],
            ai_summary=ai_summary.summary,
            generated_by=ai_summary.generated_by,
            model=ai_summary.model,
        )

    def _build_scorecard(self, payload: PullRequestUpsertRequest) -> Scorecard:
        stale_hours = _hours_since(payload.updated_at)
        stale = stale_hours >= self.settings.aggregator_stale_after_hours
        size_score = _score_size(payload.changed_files)
        churn_score = _score_churn(payload.additions, payload.deletions)
        criticality_score = _score_criticality(payload.criticality)
        stale_score = 20 if stale else min(15, stale_hours // 12)
        review_score = _score_review_status(payload.review_status)
        draft_penalty = 8 if payload.is_draft else 0
        impact_services = sorted(set(payload.impact_services))

        risk_score = _clamp(size_score + churn_score + criticality_score + draft_penalty)
        priority_score = _clamp(
            criticality_score + stale_score + review_score + min(20, len(impact_services) * 4) + (0 if payload.is_draft else 8)
        )

        return Scorecard(
            risk_score=risk_score,
            priority_score=priority_score,
            stale=stale,
            stale_hours=stale_hours,
            impact_services=impact_services,
            score_breakdown={
                "size_score": size_score,
                "churn_score": churn_score,
                "criticality_score": criticality_score,
                "stale_score": stale_score,
                "review_score": review_score,
                "draft_penalty": draft_penalty,
            },
        )

    def _to_response(self, document: dict) -> PullRequestResponse:
        response_data = dict(document)
        response_data["id"] = str(response_data.pop("_id"))
        return PullRequestResponse.model_validate(response_data)

    async def _build_resolved_payload(
        self,
        payload: PullRequestUpsertRequest,
        request: Request,
        auth_context: AuthContext,
    ) -> PullRequestUpsertRequest:
        metadata = await self.config_resolver.resolve_pull_request_metadata(payload, request, auth_context)
        return payload.model_with_resolved_metadata(
            criticality=metadata.criticality,
            impact_services=metadata.impact_services,
        )

    def _build_payload_from_document(self, document: dict) -> PullRequestUpsertRequest:
        ignored_fields = {
            "_id",
            "pr_uid",
            "risk_score",
            "priority_score",
            "stale",
            "stale_hours",
            "score_breakdown",
            "synced_at",
            "last_scored_at",
        }
        payload = {key: value for key, value in document.items() if key not in ignored_fields}
        return PullRequestUpsertRequest(**payload)

    def _raise_not_found(self, pr_id: str) -> None:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=PULL_REQUEST_NOT_FOUND_CODE,
            message=PULL_REQUEST_NOT_FOUND_MESSAGE,
            details={"pr_id": pr_id},
        )


class HttpConfigResolver:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def resolve_pull_request_metadata(
        self,
        payload: PullRequestUpsertRequest,
        request: Request,
        auth_context: AuthContext,
    ) -> ResolvedPullRequestMetadata:
        service_response = await service_request(
            "GET",
            f"{self.settings.config_service_url}/api/v1/config/repos/{payload.repository_full_name}",
            request=request,
            auth_context=auth_context,
        )
        service_config = ConfigServiceResponse.model_validate(service_response.json())

        impact_response = await service_request(
            "GET",
            f"{self.settings.config_service_url}/api/v1/config/impact/{service_config.service_name}",
            request=request,
            auth_context=auth_context,
        )
        impact = ConfigImpactResponse.model_validate(impact_response.json())
        impact_services = sorted(set(impact.direct_dependencies + impact.downstream_services))

        return ResolvedPullRequestMetadata(
            criticality=service_config.criticality,
            impact_services=impact_services,
        )


class HttpAiSummaryResolver:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def summarize_pull_request(
        self,
        pull_request: PullRequestResponse,
        request: Request,
        auth_context: AuthContext,
    ) -> AiSummaryResponse:
        response = await service_request(
            "POST",
            f"{self.settings.ai_service_url}/api/v1/ai/summaries/pr",
            request=request,
            auth_context=auth_context,
            json=AiSummaryRequest(
                repository_full_name=pull_request.repository_full_name,
                number=pull_request.number,
                title=pull_request.title,
                author_username=pull_request.author_username,
                review_status=pull_request.review_status.value,
                criticality=pull_request.criticality.value,
                changed_files=pull_request.changed_files,
                additions=pull_request.additions,
                deletions=pull_request.deletions,
                risk_score=pull_request.risk_score,
                priority_score=pull_request.priority_score,
                stale=pull_request.stale,
                impact_services=pull_request.impact_services,
                labels=pull_request.labels,
            ).model_dump(mode="json"),
        )
        return AiSummaryResponse.model_validate(response.json())


@lru_cache(maxsize=1)
def get_pull_request_repository() -> PullRequestRepository:
    return MongoPullRequestRepository(get_pull_request_collection())


def get_config_resolver(settings: Settings = Depends(get_settings)) -> ConfigResolver:
    return HttpConfigResolver(settings)


def get_ai_summary_resolver(settings: Settings = Depends(get_settings)) -> AiSummaryResolver:
    return HttpAiSummaryResolver(settings)


def get_aggregator_service(
    repository: PullRequestRepository = Depends(get_pull_request_repository),
    settings: Settings = Depends(get_settings),
    config_resolver: ConfigResolver = Depends(get_config_resolver),
    ai_summary_resolver: AiSummaryResolver = Depends(get_ai_summary_resolver),
) -> AggregatorService:
    return AggregatorService(
        repository=repository,
        settings=settings,
        config_resolver=config_resolver,
        ai_summary_resolver=ai_summary_resolver,
    )
