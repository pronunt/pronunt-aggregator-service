from fastapi import APIRouter

from app.routes.v1.aggregator import router as aggregator_router

router = APIRouter()
router.include_router(aggregator_router)
