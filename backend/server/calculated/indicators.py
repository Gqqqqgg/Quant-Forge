"""计算均线、收益率波动率和平均成交量。"""

from __future__ import annotations

import math

import pandas as pd

from server.calculated.returns import calculate_returns


def calculate_indicators(k_lines: pd.DataFrame, windows: list[int] | tuple[int, ...] = (5, 20, 60)) -> pd.DataFrame:
    """使用当天及之前的数据计算指标，窗口不足时留空。"""
    windows = list(dict.fromkeys(windows))
    if any(not isinstance(window, int) or isinstance(window, bool) or window < 2 or window > 250 for window in windows):
        raise ValueError("指标窗口必须是 2 至 250 之间的整数。")
    if "volume" not in k_lines:
        raise ValueError("复权日线缺少字段：volume")
    prices = k_lines.copy()
    missing_volume = prices["volume"].isna() | prices["volume"].astype(str).str.strip().eq("")
    prices["volume"] = pd.to_numeric(prices["volume"], errors="coerce")
    valid_volume = prices["volume"].map(lambda value: pd.notna(value) and math.isfinite(value) and value >= 0)
    if not (valid_volume | missing_volume).all():
        raise ValueError("非空成交量必须是非负的有限数值。")
    output = calculate_returns(prices)
    prices = prices.sort_values(["code", "trade_date"]).reset_index(drop=True)
    # 收益率计算已经校验并规范化日期，以股票和交易日期对齐成交量。
    volumes = prices[["code", "trade_date", "volume"]].copy()
    volumes["trade_date"] = pd.to_datetime(volumes["trade_date"]).dt.strftime("%Y-%m-%d")
    output = output.merge(volumes, on=["code", "trade_date"], validate="one_to_one")
    groups = output.groupby("code")
    for window in windows:
        output[f"ma{window}"] = groups["close"].transform(
            lambda values: values.rolling(window=window, min_periods=window).mean()
        )
        # 窗口内有效每日收益率的样本标准差，不做年化。
        output[f"volatility{window}"] = groups["daily_return"].transform(
            lambda values: values.rolling(window=window, min_periods=window).std(ddof=1)
        )
        output[f"volume_ma{window}"] = groups["volume"].transform(
            lambda values: values.rolling(window=window, min_periods=window).mean()
        )
    return output.sort_values(["code", "trade_date"]).reset_index(drop=True)
