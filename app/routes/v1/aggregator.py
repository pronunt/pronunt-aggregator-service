from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.auth import AuthContext, require_roles
from app.schemas.ai import PullRequestSummaryGenerateRequest
from app.schemas.pull_request import (
    AggregatorSummaryResponse,
    PullRequestFilters,
    PullRequestListResponse,
    PullRequestResponse,
    PullRequestSortField,
    PullRequestSummaryResponse,
    PullRequestState,
    PullRequestUpsertRequest,
    ReviewStatus,
    SortDirection,
)
from app.services.aggregator import AggregatorService, get_aggregator_service

router = APIRouter(tags=["aggregator"])
AggregatorServiceDependency = Annotated[AggregatorService, Depends(get_aggregator_service)]
AggregatorAccessDependency = Annotated[
    AuthContext,
    Depends(require_roles("developer", "reviewer", "release")),
]


def build_pull_request_filters(
    repository_full_name: str | None = None,
    author_username: str | None = None,
    state: PullRequestState | None = None,
    review_status: ReviewStatus | None = None,
    stale: bool | None = None,
    min_risk_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    min_priority_score: Annotated[int | None, Query(ge=0, le=100)] = None,
) -> PullRequestFilters:
    return PullRequestFilters(
        repository_full_name=repository_full_name,
        author_username=author_username,
        state=state,
        review_status=review_status,
        stale=stale,
        min_risk_score=min_risk_score,
        min_priority_score=min_priority_score,
    )


@router.post("/prs", status_code=status.HTTP_201_CREATED)
async def upsert_pull_request(
    payload: PullRequestUpsertRequest,
    request: Request,
    auth_context: AggregatorAccessDependency,
    service: AggregatorServiceDependency,
) -> PullRequestResponse:
    return await service.upsert_pull_request(payload, request, auth_context)


@router.get("/prs")
def list_pull_requests(
    filters: Annotated[PullRequestFilters, Depends(build_pull_request_filters)],
    _: AggregatorAccessDependency,
    service: AggregatorServiceDependency,
    sort_by: PullRequestSortField = PullRequestSortField.priority_score,
    sort_direction: SortDirection = SortDirection.desc,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PullRequestListResponse:
    return service.list_pull_requests(filters, sort_by, sort_direction, limit, offset)


@router.get("/prs/{pr_id}")
def get_pull_request(
    pr_id: str,
    _: AggregatorAccessDependency,
    service: AggregatorServiceDependency,
) -> PullRequestResponse:
    return service.get_pull_request(pr_id)


@router.post("/prs/{pr_id}/score")
async def recompute_pull_request_scores(
    pr_id: str,
    request: Request,
    auth_context: AggregatorAccessDependency,
    service: AggregatorServiceDependency,
) -> PullRequestResponse:
    return await service.recompute_pull_request_scores(pr_id, request, auth_context)


@router.post("/prs/{pr_id}/summary")
async def generate_pull_request_summary(
    pr_id: str,
    request: Request,
    auth_context: AggregatorAccessDependency,
    service: AggregatorServiceDependency,
    payload: PullRequestSummaryGenerateRequest | None = None,
) -> PullRequestSummaryResponse:
    provider_override = payload.provider_override if payload is not None else None
    return await service.generate_pull_request_summary(pr_id, request, auth_context, provider_override=provider_override)


@router.get("/summary")
def get_summary(
    _: AggregatorAccessDependency,
    service: AggregatorServiceDependency,
) -> AggregatorSummaryResponse:
    return service.get_summary()
