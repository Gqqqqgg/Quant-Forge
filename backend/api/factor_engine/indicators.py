from fastapi import APIRouter

from api.factor_engine.request import FactorEngineRequest
from api.factor_engine.response import FactorEngineResponse, execute

router = APIRouter()


@router.post("/factor_engine/indicators")
def calculate_indicators(request: FactorEngineRequest) -> FactorEngineResponse:
    return execute(request, "indicators")
