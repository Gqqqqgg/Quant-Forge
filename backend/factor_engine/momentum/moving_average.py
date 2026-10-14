"""按交易日窗口计算价格均线。"""

import pandas as pd


def calculate_moving_average(prices: pd.Series, window: int) -> pd.Series:
    """包含当日价格，窗口不足时留空。"""
    return prices.rolling(window=window, min_periods=window).mean()
