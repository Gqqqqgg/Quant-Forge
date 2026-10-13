from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query

from api.calculated.request import CalculationRequest
from api.calculated.response import CalculationResponse, execute

router = APIRouter()


@router.post("/calculated/charts")
def calculate_charts(request: CalculationRequest) -> CalculationResponse:
    """一次返回前端所需的价格、成交量、收益率和指标。"""

    return execute(request, "charts")


@router.get("/stocks/{symbol}/charts")
def get_stock_charts(
    symbol: Annotated[str, Path(pattern=r"^(sh|sz|bj)\.\d{6}$")],
    source: Literal["baostock", "tushare"] = "tushare",
    start_date: date | None = None,
    end_date: date | None = None,
    adjust_type: Literal["qfq", "hfq"] = "hfq",
    windows: Annotated[list[int] | None, Query()] = None,
) -> CalculationResponse:
    return calculate_charts(
        CalculationRequest(
            source=source,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
            windows=windows if windows is not None else [5, 20, 60],
        )
    )
