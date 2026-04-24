from fastapi import APIRouter, Depends, Query, status

from app.core.auth import AuthContext, require_roles
from app.schemas.pull_request import (
    AggregatorSummaryResponse,
    PullRequestFilters,
    PullRequestListResponse,
    PullRequestResponse,
    PullRequestSortField,
    PullRequestState,
    PullRequestUpsertRequest,
    ReviewStatus,
    SortDirection,
)
from app.services.aggregator import AggregatorService, get_aggregator_service

router = APIRouter(tags=["aggregator"])
aggregator_access_dependency = Depends(require_roles("developer", "reviewer", "release"))


@router.post("/prs", response_model=PullRequestResponse, status_code=status.HTTP_201_CREATED)
def upsert_pull_request(
    payload: PullRequestUpsertRequest,
    _: AuthContext = aggregator_access_dependency,
    service: AggregatorService = Depends(get_aggregator_service),
) -> PullRequestResponse:
    return service.upsert_pull_request(payload)


@router.get("/prs", response_model=PullRequestListResponse)
def list_pull_requests(
    repository_full_name: str | None = None,
    author_username: str | None = None,
    state: PullRequestState | None = None,
    review_status: ReviewStatus | None = None,
    stale: bool | None = None,
    min_risk_score: int | None = Query(default=None, ge=0, le=100),
    min_priority_score: int | None = Query(default=None, ge=0, le=100),
    sort_by: PullRequestSortField = PullRequestSortField.priority_score,
    sort_direction: SortDirection = SortDirection.desc,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: AuthContext = aggregator_access_dependency,
    service: AggregatorService = Depends(get_aggregator_service),
) -> PullRequestListResponse:
    filters = PullRequestFilters(
        repository_full_name=repository_full_name,
        author_username=author_username,
        state=state,
        review_status=review_status,
        stale=stale,
        min_risk_score=min_risk_score,
        min_priority_score=min_priority_score,
    )
    return service.list_pull_requests(filters, sort_by, sort_direction, limit, offset)


@router.get("/prs/{pr_id}", response_model=PullRequestResponse)
def get_pull_request(
    pr_id: str,
    _: AuthContext = aggregator_access_dependency,
    service: AggregatorService = Depends(get_aggregator_service),
) -> PullRequestResponse:
    return service.get_pull_request(pr_id)


@router.post("/prs/{pr_id}/score", response_model=PullRequestResponse)
def recompute_pull_request_scores(
    pr_id: str,
    _: AuthContext = aggregator_access_dependency,
    service: AggregatorService = Depends(get_aggregator_service),
) -> PullRequestResponse:
    return service.recompute_pull_request_scores(pr_id)


@router.get("/summary", response_model=AggregatorSummaryResponse)
def get_summary(
    _: AuthContext = aggregator_access_dependency,
    service: AggregatorService = Depends(get_aggregator_service),
) -> AggregatorSummaryResponse:
    return service.get_summary()
