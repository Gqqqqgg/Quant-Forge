from fastapi import APIRouter

from api.calculated.request import CalculationRequest
from api.calculated.response import CalculationResponse, execute

router = APIRouter()


@router.post("/calculated/indicators")
def calculate_indicators(request: CalculationRequest) -> CalculationResponse:
    return execute(request, "indicators")
