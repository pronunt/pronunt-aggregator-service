from pydantic import BaseModel, Field


class AiSummaryRequest(BaseModel):
    repository_full_name: str
    number: int = Field(..., ge=1)
    title: str
    author_username: str
    review_status: str
    criticality: str
    changed_files: int = Field(..., ge=0)
    additions: int = Field(..., ge=0)
    deletions: int = Field(..., ge=0)
    risk_score: int = Field(..., ge=0, le=100)
    priority_score: int = Field(..., ge=0, le=100)
    stale: bool
    impact_services: list[str]
    labels: list[str]


class AiSummaryResponse(BaseModel):
    summary: str
    generated_by: str
    model: str
