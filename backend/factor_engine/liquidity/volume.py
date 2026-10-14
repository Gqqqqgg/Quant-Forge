"""按交易日窗口计算平均成交量。"""

import pandas as pd


def calculate_average_volume(volumes: pd.Series, window: int) -> pd.Series:
    """包含当日成交量，窗口内有缺失值时留空。"""
    return volumes.rolling(window=window, min_periods=window).mean()
