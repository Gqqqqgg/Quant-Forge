from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class FactorEngineRequest(BaseModel):
    """前端传入股票、日期、复权方式和指标窗口。"""

    source: Literal["baostock", "tushare"] = "tushare"
    symbol: str = Field(pattern=r"^(sh|sz|bj)\.\d{6}$")
    start_date: date | None = None
    end_date: date | None = None
    adjust_type: Literal["qfq", "hfq"] = "hfq"
    windows: list[int] = Field(default_factory=lambda: [5, 20, 60])
