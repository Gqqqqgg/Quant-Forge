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


INDEX_NAMES = {
    "sh.000001": ("上证指数", "指数"),
    "sz.399001": ("深证成指", "指数"),
    "sz.399006": ("创业板指", "指数"),
    "sh.000016": ("上证50", "指数"),
    "sh.000905": ("中证500", "指数"),
    "sh.000300": ("沪深300", "指数"),
}

SECURITY_NAMES = STOCK_NAMES | INDEX_NAMES


@router.get("/stocks")
def get_stocks(source: Literal["baostock", "tushare"] = "tushare") -> dict:
    """列出 STOCK_NAMES 中已有原始日线的股票。"""
    directory = DataService().row_store.root / source / "row" / "k_line"
    stocks = []
    for path in sorted(directory.glob("*.parquet")):
        if path.stem not in STOCK_NAMES:
            continue
        frame = pd.read_parquet(path, columns=["trade_date"])
        if frame.empty:
            continue
        name, industry = STOCK_NAMES[path.stem]
        stocks.append(
            {
                "symbol": path.stem,
                "name": name,
                "industry": industry,
                "asset_type": "stock",
                "rows": len(frame),
                "start_date": str(frame["trade_date"].min()),
                "end_date": str(frame["trade_date"].max()),
            }
        )
    return {"source": source, "stocks": stocks}


@router.get("/indexs")
def get_indexs(source: Literal["baostock", "tushare"] = "tushare") -> dict:
    """列出 INDEX_NAMES 中已有原始日线的指数。"""
    directory = DataService().row_store.root / source / "row" / "k_line"
    indexs = []
    for path in sorted(directory.glob("*.parquet")):
        if path.stem not in INDEX_NAMES:
            continue
        frame = pd.read_parquet(path, columns=["trade_date"])
        if frame.empty:
            continue
        name, industry = INDEX_NAMES[path.stem]
        indexs.append(
            {
                "symbol": path.stem,
                "name": name,
                "industry": industry,
                "asset_type": "index",
                "rows": len(frame),
                "start_date": str(frame["trade_date"].min()),
                "end_date": str(frame["trade_date"].max()),
            }
        )
    return {"source": source, "indexs": indexs}
