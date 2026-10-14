"""基于收盘价计算历史最高点到后续低点的最大回撤。"""

import pandas as pd

from factor_engine.momentum.returns import calculate_returns


def calculate_max_drawdown(k_lines: pd.DataFrame) -> float:
    """按收盘价计算区间峰值到后续谷值的最大跌幅，返回非负比例。"""
    prices = calculate_returns(k_lines)
    peaks = prices.groupby("code")["close"].cummax()
    return float((1 - prices["close"] / peaks).max())
