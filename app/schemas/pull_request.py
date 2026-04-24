from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class PullRequestState(str, Enum):
    open = "open"
    closed = "closed"
    merged = "merged"


class ReviewStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    changes_requested = "changes_requested"
    commented = "commented"


class ServiceCriticality(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class PullRequestUpsertRequest(BaseModel):
    repository_full_name: str = Field(..., examples=["pronunt/pronunt-aggregator-service"])
    repository_owner: str
    repository_name: str
    number: int = Field(..., ge=1)
    title: str
    author_username: str
    state: PullRequestState = PullRequestState.open
    review_status: ReviewStatus = ReviewStatus.pending
    is_draft: bool = False
    html_url: str | None = None
    base_branch: str
    head_branch: str
    labels: list[str] = Field(default_factory=list)
    changed_files: int = Field(default=0, ge=0)
    additions: int = Field(default=0, ge=0)
    deletions: int = Field(default=0, ge=0)
    criticality: ServiceCriticality = ServiceCriticality.medium
    created_at: datetime
    updated_at: datetime
    merged_at: datetime | None = None
    closed_at: datetime | None = None
    impact_services: list[str] = Field(default_factory=list)
    ai_summary: str | None = None


class ScoreBreakdown(BaseModel):
    size_score: int
    churn_score: int
    criticality_score: int
    stale_score: int
    review_score: int
    draft_penalty: int


class PullRequestResponse(BaseModel):
    id: str
    pr_uid: str
    repository_full_name: str
    repository_owner: str
    repository_name: str
    number: int
    title: str
    author_username: str
    state: PullRequestState
    review_status: ReviewStatus
    is_draft: bool
    html_url: str | None = None
    base_branch: str
    head_branch: str
    labels: list[str]
    changed_files: int
    additions: int
    deletions: int
    criticality: ServiceCriticality
    created_at: datetime
    updated_at: datetime
    merged_at: datetime | None = None
    closed_at: datetime | None = None
    ai_summary: str | None = None
    risk_score: int
    priority_score: int
    stale: bool
    stale_hours: int
    impact_services: list[str]
    score_breakdown: ScoreBreakdown
    synced_at: datetime
    last_scored_at: datetime


class PullRequestListResponse(BaseModel):
    items: list[PullRequestResponse]
    total: int


class AggregatorSummaryResponse(BaseModel):
    total_open: int
    total_stale: int
    total_high_risk: int
    total_high_priority: int
    by_criticality: dict[str, int]


class PullRequestFilters(BaseModel):
    repository_full_name: str | None = None
    author_username: str | None = None
    state: PullRequestState | None = None
    review_status: ReviewStatus | None = None
    stale: bool | None = None
    min_risk_score: int | None = Field(default=None, ge=0, le=100)
    min_priority_score: int | None = Field(default=None, ge=0, le=100)


class PullRequestSortField(str, Enum):
    updated_at = "updated_at"
    priority_score = "priority_score"
    risk_score = "risk_score"
    created_at = "created_at"


class SortDirection(str, Enum):
    asc = "asc"
    desc = "desc"
