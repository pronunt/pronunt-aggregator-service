from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/v1/health")
def versioned_health() -> dict[str, str]:
    return {"status": "ok"}
