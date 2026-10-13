from fastapi import APIRouter

from api.calculated.request import CalculationRequest
from api.calculated.response import CalculationResponse, execute

router = APIRouter()


@router.post("/calculated/returns")
def calculate_returns(request: CalculationRequest) -> CalculationResponse:
    return execute(request, "returns")
