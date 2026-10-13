from fastapi import APIRouter

from api.calculated.request import CalculationRequest
from api.calculated.response import CalculationResponse, execute

router = APIRouter()


@router.post("/calculated/adjustment")
def calculate_adjustment(request: CalculationRequest) -> CalculationResponse:
    return execute(request, "adjustment")
