"""调用计算服务，转换 HTTP 错误并组装统一响应。"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel

from api.calculated.request import CalculationRequest
from api.stocks import STOCK_NAMES
from server.calculated.service import CalculationService, DateRangeError


class CalculationResponse(BaseModel):
    """统一的计算响应，指标列随请求窗口动态变化。"""

    source: Literal["baostock", "tushare"]
    symbol: str
    name: str
    industry: str
    adjust_type: Literal["qfq", "hfq"]
    windows: list[int]
    baseline_date: date
    rows: int
    data: list[dict[str, Any]]


def execute(request: CalculationRequest, dataset: str) -> CalculationResponse:
    try:
        frame = CalculationService().calculate(dataset=dataset, **request.model_dump())
    except DateRangeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    name, industry = STOCK_NAMES.get(request.symbol, (request.symbol, "股票"))
    return CalculationResponse(
        **{
            "source": request.source,
            "symbol": request.symbol,
            "name": name,
            "industry": industry,
            "adjust_type": request.adjust_type,
            "windows": list(dict.fromkeys(request.windows)),
            "baseline_date": str(frame["trade_date"].iloc[0]),
            "rows": len(frame),
            "data": json.loads(frame.to_json(orient="records", double_precision=10)),
        }
    )
