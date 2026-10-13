from __future__ import annotations

from typing import Literal

import pandas as pd
from fastapi import APIRouter

from market_data.service import DataService

router = APIRouter()

STOCK_NAMES = {
    "sh.600519": ("贵州茅台", "白酒"),
    "sh.600036": ("招商银行", "银行"),
    "sz.000333": ("美的集团", "家电"),
    "sz.300750": ("宁德时代", "动力电池"),
    "sh.600900": ("长江电力", "水电"),
}


@router.get("/stocks")
def get_stocks(source: Literal["baostock", "tushare"] = "tushare") -> dict:
    """列出已有原始日线的股票，无需提前生成计算文件。"""
    directory = DataService().row_store.root / source / "row" / "k_line"
    stocks = []
    for path in sorted(directory.glob("*.parquet")):
        frame = pd.read_parquet(path, columns=["trade_date"])
        if frame.empty:
            continue
        name, industry = STOCK_NAMES.get(path.stem, (path.stem, "股票"))
        stocks.append(
            {
                "symbol": path.stem,
                "name": name,
                "industry": industry,
                "rows": len(frame),
                "start_date": str(frame["trade_date"].min()),
                "end_date": str(frame["trade_date"].max()),
            }
        )
    return {"source": source, "stocks": stocks}
