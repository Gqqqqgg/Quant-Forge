"""复权、收益率、指标及图表计算接口。"""

from fastapi import APIRouter

from api.calculated import adjustment, charts, indicators, returns

router = APIRouter()
for module in (adjustment, returns, indicators, charts):
    router.include_router(module.router)
