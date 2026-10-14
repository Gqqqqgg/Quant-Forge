"""读取原始日线，使用 BaoStock 累计因子计算前复权和后复权日线。"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd

from market_data.storage.root_path import get_data_root


class DateRangeError(ValueError):
    """请求日期顺序错误。"""


def select_date_range(frame: pd.DataFrame, start_date: date | None = None) -> pd.DataFrame:
    """截取计算后的日期区间，统一行情数值字段。"""
    if start_date:
        frame = frame[frame["trade_date"] >= start_date.isoformat()].copy()
    if frame.empty:
        raise FileNotFoundError("所选日期区间没有行情。")
    for column in ("open", "high", "low", "close", "preclose", "volume"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def get_raw_k_line(
    symbol: str,
    source: str = "tushare",
    start_date: date | None = None,
    end_date: date | None = None,
    root: Path | None = None,
) -> pd.DataFrame:
    """读取指定区间的不复权日线，无需复权因子。"""
    if start_date and end_date and start_date > end_date:
        raise DateRangeError("开始日期不能晚于结束日期。")
    if source not in {"baostock", "tushare"}:
        raise ValueError(f"不支持的数据源：{source}")
    data_root = (root if root is not None else get_data_root()) / source / "row"
    k_line_path = data_root / "k_line" / f"{symbol}.parquet"
    if not k_line_path.exists():
        raise FileNotFoundError("未找到股票的原始日线，请先完成同步。")
    k_lines = pd.read_parquet(k_line_path)
    if k_lines.empty or set(k_lines["code"]) != {symbol}:
        raise ValueError("原始日线为空或包含其他股票。")
    frame = calculate_adjusted_k_line(k_lines, pd.DataFrame(), "none")
    if end_date:
        frame = frame[frame["trade_date"] <= end_date.isoformat()].copy()
    return select_date_range(frame, start_date)


def get_adjusted_k_line(
    symbol: str,
    source: str = "tushare",
    start_date: date | None = None,
    end_date: date | None = None,
    adjust_type: Literal["none", "qfq", "hfq"] = "hfq",
    root: Path | None = None,
) -> pd.DataFrame:
    """返回指定区间的日线，none 保留原始价格且不读取因子。"""
    if adjust_type == "none":
        return get_raw_k_line(symbol, source, start_date, end_date, root)
    if start_date and end_date and start_date > end_date:
        raise DateRangeError("开始日期不能晚于结束日期。")
    if source != "baostock":
        raise NotImplementedError("尚未实现 Tushare 的复权因子转换。")
    data_root = (root if root is not None else get_data_root()) / source / "row"
    k_line_path = data_root / "k_line" / f"{symbol}.parquet"
    factor_path = data_root / "adjust_factor" / f"{symbol}.parquet"
    if not k_line_path.exists() or not factor_path.exists():
        raise FileNotFoundError("未找到股票的原始日线或复权因子，请先完成同步。")
    k_lines = pd.read_parquet(k_line_path)
    factors = pd.read_parquet(factor_path)
    if k_lines.empty or set(k_lines["code"]) != {symbol}:
        raise ValueError("原始日线为空或包含其他股票。")
    if factors.empty or set(factors["code"]) != {symbol}:
        raise ValueError("复权因子为空或包含其他股票。")
    if end_date:
        k_lines = k_lines[k_lines["trade_date"] <= end_date.isoformat()]
    if k_lines.empty:
        raise FileNotFoundError("所选日期区间没有行情。")
    return select_date_range(calculate_adjusted_k_line(k_lines, factors, adjust_type), start_date)


def calculate_adjusted_k_line(
    k_lines: pd.DataFrame,
    factors: pd.DataFrame,
    adjust_type: Literal["none", "qfq", "hfq"],
) -> pd.DataFrame:
    """按股票匹配当天已生效的因子，返回新的复权行情表。"""
    factor_columns = {"qfq": "foreAdjustFactor", "hfq": "backAdjustFactor"}
    if adjust_type not in {"none", *factor_columns}:
        raise ValueError(f"不支持的复权类型：{adjust_type}")
    factor_column = factor_columns.get(adjust_type)
    inputs = [(k_lines, {"code", "trade_date", "open", "high", "low", "close"}, "原始日线")]
    if adjust_type != "none":
        inputs.append((factors, {"code", "dividOperateDate", factor_column}, "复权因子"))
    for frame, required, label in inputs:
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"{label}缺少字段：{', '.join(sorted(missing))}")
        if frame["code"].isna().any():
            raise ValueError(f"{label}包含空股票代码。")

    output = k_lines.copy()
    output["trade_date"] = pd.to_datetime(output["trade_date"], errors="raise")
    if output["trade_date"].isna().any():
        raise ValueError("日线包含空日期。")
    if output.duplicated(["code", "trade_date"]).any():
        raise ValueError("原始日线包含重复的股票和交易日期。")
    price_columns = [column for column in ("open", "high", "low", "close", "preclose") if column in output]
    for column in price_columns:
        output[column] = pd.to_numeric(output[column], errors="raise")
        if not output[column].map(lambda value: pd.notna(value) and math.isfinite(value)).all():
            raise ValueError(f"价格字段 {column} 包含空值或非有限数值。")
    if adjust_type == "none":
        output["trade_date"] = output["trade_date"].dt.strftime("%Y-%m-%d")
        output["adjust_type"] = "none"
        return output.sort_values(["code", "trade_date"]).reset_index(drop=True)

    events = factors[["code", "dividOperateDate", factor_column]].copy()
    events["dividOperateDate"] = pd.to_datetime(events["dividOperateDate"], errors="raise")
    if output["trade_date"].isna().any() or events["dividOperateDate"].isna().any():
        raise ValueError("日线或复权因子包含空日期。")
    if events.duplicated(["code", "dividOperateDate"]).any():
        raise ValueError("复权因子包含重复的股票和生效日期。")
    events[factor_column] = pd.to_numeric(events[factor_column], errors="raise")
    valid_factors = events[factor_column].map(lambda value: pd.notna(value) and math.isfinite(value) and value > 0)
    if not valid_factors.all():
        raise ValueError("复权因子必须是正的有限数值。")

    events = events.rename(columns={"dividOperateDate": "factor_date", factor_column: "price_factor"})
    output = pd.merge_asof(
        output.sort_values(["trade_date", "code"]),
        events.sort_values(["factor_date", "code"]),
        left_on="trade_date",
        right_on="factor_date",
        by="code",
        direction="backward",
        allow_exact_matches=True,
    )
    missing = output["price_factor"].isna()
    if missing.any():
        first = output.loc[missing].iloc[0]
        raise ValueError(f"{first['code']} 在 {first['trade_date'].date()} 缺少已生效因子，请补齐起始日前的因子记录。")
    for column in price_columns:
        output[column] = output[column] * output["price_factor"]
    output["trade_date"] = output["trade_date"].dt.strftime("%Y-%m-%d")
    output["factor_date"] = output["factor_date"].dt.strftime("%Y-%m-%d")
    output["adjust_type"] = adjust_type
    return output.sort_values(["code", "trade_date"]).reset_index(drop=True)
