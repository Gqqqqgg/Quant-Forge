from fastapi import APIRouter

from api import calculated, stocks

router = APIRouter(prefix="/api")
router.include_router(stocks.router)
router.include_router(calculated.router)
