"""按共同交易日期比较证券与基准的区间表现。"""

from __future__ import annotations

import pandas as pd

from factor_engine.momentum.returns import calculate_returns


def calculate_relative_strength(k_lines: pd.DataFrame, benchmark: pd.DataFrame) -> pd.DataFrame:
    """双方从首个共同交易日归一到 100，超额收益为累计收益之差。"""
    if k_lines["code"].nunique() != 1 or benchmark["code"].nunique() != 1:
        raise ValueError("相对强弱每次只能比较一个证券和一个基准。")
    prices = calculate_returns(k_lines)[["trade_date", "close"]]
    benchmark_prices = calculate_returns(benchmark)[["trade_date", "close"]].rename(
        columns={"close": "benchmark_close"}
    )
    output = prices.merge(benchmark_prices, on="trade_date", how="inner", validate="one_to_one")
    if output.empty:
        raise ValueError("所选区间内证券与基准没有共同交易日期。")
    output = output.sort_values("trade_date").reset_index(drop=True)
    output["security_return"] = output["close"] / output["close"].iloc[0] - 1
    output["benchmark_return"] = output["benchmark_close"] / output["benchmark_close"].iloc[0] - 1
    output["security_normalized"] = (1 + output["security_return"]) * 100
    output["benchmark_normalized"] = (1 + output["benchmark_return"]) * 100
    output["excess_return"] = output["security_return"] - output["benchmark_return"]
    return output
