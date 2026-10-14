from fastapi import APIRouter

from api.factor_engine.request import FactorEngineRequest
from api.factor_engine.response import FactorEngineResponse, execute

router = APIRouter()


@router.post("/factor_engine/adjustment")
def calculate_adjustment(request: FactorEngineRequest) -> FactorEngineResponse:
    return execute(request, "adjustment")
