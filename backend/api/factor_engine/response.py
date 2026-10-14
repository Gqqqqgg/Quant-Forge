"""调用计算服务，转换 HTTP 错误并组装统一响应。"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel

from api.factor_engine.request import FactorEngineRequest
from api.stocks import INDEX_NAMES, SECURITY_NAMES
from factor_engine.adjustment import DateRangeError, get_adjusted_k_line
from factor_engine.indicators import get_indicators
from factor_engine.returns import get_returns


class FactorEngineResponse(BaseModel):
    """统一的计算响应，指标列随请求窗口动态变化。"""

    source: Literal["baostock", "tushare"]
    symbol: str
    name: str
    industry: str
    adjust_type: Literal["none", "qfq", "hfq"]
    windows: list[int]
    baseline_date: date
    rows: int
    data: list[dict[str, Any]]


def execute(request: FactorEngineRequest, dataset: str) -> FactorEngineResponse:
    name, industry = SECURITY_NAMES.get(request.symbol, (request.symbol, "股票"))
    if request.symbol in INDEX_NAMES and request.adjust_type != "none":
        raise HTTPException(status_code=422, detail="指数请使用不复权模式（adjust_type=none）。")
    try:
        parameters = request.model_dump()
        if dataset == "adjustment":
            parameters.pop("windows")
            frame = get_adjusted_k_line(**parameters)
        elif dataset == "returns":
            parameters.pop("windows")
            frame = get_returns(**parameters)
        elif dataset in {"indicators", "charts"}:
            frame = get_indicators(**parameters, include_prices=dataset == "charts")
        else:
            raise ValueError(f"不支持的计算类型：{dataset}")
    except DateRangeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FactorEngineResponse(
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
