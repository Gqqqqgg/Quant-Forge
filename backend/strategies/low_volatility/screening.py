"""计算股票池的因子快照，按条件筛选并返回入选依据。"""

import math
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd

from factor_engine.liquidity.volume import calculate_average_volume
from factor_engine.momentum.moving_average import calculate_moving_average
from factor_engine.momentum.relative_strength import calculate_relative_strength
from factor_engine.momentum.returns import calculate_returns, select_returns_date_range
from factor_engine.risk.drawdown import calculate_max_drawdown
from factor_engine.risk.volatility import calculate_volatility
from market_data.adjustment import DateRangeError, get_adjusted_k_line, get_raw_k_line
from strategies.low_volatility.definition import INDEX_NAMES, STOCK_NAMES, StrategyDefinition


def load_factors(
    symbol: str,
    source: str = "tushare",
    start_date: date | None = None,
    end_date: date | None = None,
    adjust_type: Literal["none", "qfq", "hfq"] = "hfq",
    windows: list[int] | tuple[int, ...] = (5, 20, 60),
    root: Path | None = None,
) -> pd.DataFrame:
    """读取行情并预热本策略的因子，再截取请求区间。"""
    if start_date and end_date and start_date > end_date:
        raise DateRangeError("开始日期不能晚于结束日期。")
    adjusted = get_adjusted_k_line(symbol, source, end_date=end_date, adjust_type=adjust_type, root=root)
    frame = calculate_factors(adjusted, windows)
    return select_returns_date_range(frame, start_date)


def calculate_factors(k_lines: pd.DataFrame, windows: list[int] | tuple[int, ...] = (5, 20, 60)) -> pd.DataFrame:
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
        output[f"ma{window}"] = groups["close"].transform(lambda values: calculate_moving_average(values, window))
        # 窗口内有效每日收益率的样本标准差，不做年化。
        output[f"volatility{window}"] = groups["daily_return"].transform(
            lambda values: calculate_volatility(values, window)
        )
        output[f"volume_ma{window}"] = groups["volume"].transform(
            lambda values: calculate_average_volume(values, window)
        )
    return output.sort_values(["code", "trade_date"]).reset_index(drop=True)


def finite_value(value) -> float | None:
    return float(value) if pd.notna(value) and math.isfinite(value) else None


def run_screening(definition: StrategyDefinition) -> dict:
    if definition.benchmark_symbol is not None and definition.benchmark_symbol not in INDEX_NAMES:
        raise ValueError("请选择配置的基准指数。")
    benchmark = None
    benchmark_error = None
    if definition.benchmark_symbol:
        try:
            benchmark = get_raw_k_line(
                definition.benchmark_symbol, definition.source, definition.start_date, definition.end_date
            )
        except (ValueError, FileNotFoundError, NotImplementedError) as exc:
            benchmark_error = str(exc)
    candidates = []
    excluded = []
    errors = []
    for symbol, (name, industry) in STOCK_NAMES.items():
        try:
            frame = load_factors(
                symbol,
                definition.source,
                definition.start_date,
                definition.end_date,
                definition.adjust_type,
                windows=[20, 60],
            )
            latest = frame.iloc[-1]
            metrics = {
                "range_return": float(latest["cumulative_return"]),
                "max_drawdown": calculate_max_drawdown(frame),
                "volatility": finite_value(frame["daily_return"].iloc[1:].std(ddof=1)),
                "ma20_deviation": finite_value(latest["close"] / latest["ma20"] - 1) if latest["ma20"] > 0 else None,
                "ma60_deviation": finite_value(latest["close"] / latest["ma60"] - 1) if latest["ma60"] > 0 else None,
                "volume_ratio": (
                    finite_value(latest["volume"] / latest["volume_ma20"]) if latest["volume_ma20"] > 0 else None
                ),
                "excess_return": None,
            }
            relative_error = benchmark_error
            if benchmark is not None:
                try:
                    relative = calculate_relative_strength(frame, benchmark)
                    # 统一使用股票实际区间的起止日，避免基准覆盖不足改变筛选口径。
                    if (
                        relative["trade_date"].iloc[0] != frame["trade_date"].iloc[0]
                        or relative["trade_date"].iloc[-1] != latest["trade_date"]
                    ):
                        relative_error = "基准未覆盖股票实际区间的起止交易日。"
                    else:
                        metrics["excess_return"] = float(relative["excess_return"].iloc[-1])
                except ValueError as exc:
                    relative_error = str(exc)
            checks = []
            for rule in definition.conditions:
                actual = metrics[rule.metric]
                passed = actual is not None and (
                    actual >= rule.value if rule.operator == "gte" else actual <= rule.value
                )
                checks.append({**rule.model_dump(), "actual": actual, "passed": passed})
            item = {
                "symbol": symbol,
                "name": name,
                "industry": industry,
                "start_date": frame["trade_date"].iloc[0],
                "end_date": latest["trade_date"],
                "rows": len(frame),
                "metrics": metrics,
                "checks": checks,
                "comparison_error": relative_error,
            }
            if all(check["passed"] for check in checks):
                candidates.append(item)
            else:
                excluded.append(item)
        except (ValueError, FileNotFoundError, NotImplementedError) as exc:
            errors.append({"symbol": symbol, "name": name, "error": str(exc)})
    available = [item for item in candidates if item["metrics"][definition.sort_by] is not None]
    missing = [item for item in candidates if item["metrics"][definition.sort_by] is None]
    available.sort(key=lambda item: item["metrics"][definition.sort_by], reverse=definition.sort_direction == "desc")
    return {
        "definition": definition.model_dump(mode="json"),
        "total": len(STOCK_NAMES),
        "matched": len(candidates),
        "candidates": available + missing,
        "excluded": excluded,
        "errors": errors,
    }
