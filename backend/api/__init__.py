from fastapi import APIRouter

from api import factor_engine, stocks

router = APIRouter(prefix="/api")
router.include_router(stocks.router)
router.include_router(factor_engine.router)
