"""按交易日窗口计算每日收益率波动率。"""

import pandas as pd


def calculate_volatility(returns: pd.Series, window: int) -> pd.Series:
    """返回窗口内有效每日收益率的样本标准差，不做年化。"""
    return returns.rolling(window=window, min_periods=window).std(ddof=1)
