"""基于复权收盘价计算每日收益率和累计收益率。"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd

from factor_engine.adjustment import DateRangeError, get_adjusted_k_line, select_date_range


def select_returns_date_range(frame: pd.DataFrame, start_date: date | None = None) -> pd.DataFrame:
    """保留历史每日收益率，将累计收益基准设为请求区间首日。"""
    frame = select_date_range(frame, start_date)
    frame["cumulative_return"] = frame["close"] / frame["close"].iloc[0] - 1
    return frame


def get_returns(
    symbol: str,
    source: str = "tushare",
    start_date: date | None = None,
    end_date: date | None = None,
    adjust_type: Literal["qfq", "hfq"] = "hfq",
    root: Path | None = None,
) -> pd.DataFrame:
    """先计算历史每日收益，再截取请求区间并设置累计收益基准。"""
    if start_date and end_date and start_date > end_date:
        raise DateRangeError("开始日期不能晚于结束日期。")
    adjusted = get_adjusted_k_line(symbol, source, end_date=end_date, adjust_type=adjust_type, root=root)
    return select_returns_date_range(calculate_returns(adjusted), start_date)


def calculate_returns(k_lines: pd.DataFrame) -> pd.DataFrame:
    """按股票计算收盘到收盘的收益；首日每日收益为空，累计收益为零。"""
    required = {"code", "trade_date", "close"}
    missing = required.difference(k_lines.columns)
    if missing:
        raise ValueError(f"复权日线缺少字段：{', '.join(sorted(missing))}")
    if k_lines.empty:
        raise ValueError("复权日线为空。")
    columns = ["code", "trade_date", "close"]
    if "adjust_type" in k_lines:
        columns.append("adjust_type")
    output = k_lines[columns].copy()
    if output["code"].isna().any():
        raise ValueError("复权日线包含空股票代码。")
    output["trade_date"] = pd.to_datetime(output["trade_date"], errors="coerce")
    if output["trade_date"].isna().any():
        raise ValueError("复权日线包含空日期或无效日期。")
    if output.duplicated(["code", "trade_date"]).any():
        raise ValueError("复权日线包含重复的股票和交易日期。")
    output["close"] = pd.to_numeric(output["close"], errors="coerce")
    valid_prices = output["close"].map(lambda value: pd.notna(value) and math.isfinite(value) and value > 0)
    if not valid_prices.all():
        raise ValueError("复权收盘价必须是正的有限数值。")
    output = output.sort_values(["code", "trade_date"]).reset_index(drop=True)
    closes = output.groupby("code")["close"]
    output["daily_return"] = closes.pct_change(fill_method=None)
    output["cumulative_return"] = output["close"] / closes.transform("first") - 1
    output["trade_date"] = output["trade_date"].dt.strftime("%Y-%m-%d")
    return output
