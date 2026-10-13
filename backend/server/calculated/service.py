"""读取原始数据并组织内存计算，不依赖 API 或写入计算文件。"""

from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd

from market_data.service import DataService
from server.calculated.adjustment import calculate_adjusted_k_line
from server.calculated.indicators import calculate_indicators
from server.calculated.returns import calculate_returns


class DateRangeError(ValueError):
    """请求日期顺序错误。"""


class CalculationService:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else DataService().row_store.root

    def calculate(
        self,
        dataset: Literal["adjustment", "returns", "indicators", "charts"],
        symbol: str,
        source: str = "tushare",
        start_date: date | None = None,
        end_date: date | None = None,
        adjust_type: Literal["qfq", "hfq"] = "hfq",
        windows: list[int] | tuple[int, ...] = (5, 20, 60),
    ) -> pd.DataFrame:
        """先计算历史窗口，再截取日期区间并设置累计收益基准。"""
        if start_date and end_date and start_date > end_date:
            raise DateRangeError("开始日期不能晚于结束日期。")
        if source != "baostock":
            raise NotImplementedError("尚未实现 Tushare 的复权因子转换。")
        root = self.root / source / "row"
        k_line_path = root / "k_line" / f"{symbol}.parquet"
        factor_path = root / "adjust_factor" / f"{symbol}.parquet"
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
        adjusted = calculate_adjusted_k_line(k_lines, factors, adjust_type)
        if dataset == "adjustment":
            frame = adjusted
        elif dataset == "returns":
            frame = calculate_returns(adjusted)
        elif dataset in {"indicators", "charts"}:
            frame = calculate_indicators(adjusted, windows)
            if dataset == "charts":
                frame = adjusted[["code", "trade_date", "open", "high", "low"]].merge(
                    frame, on=["code", "trade_date"], validate="one_to_one"
                )
        else:
            raise ValueError(f"不支持的计算类型：{dataset}")
        if start_date:
            frame = frame[frame["trade_date"] >= start_date.isoformat()].copy()
        if frame.empty:
            raise FileNotFoundError("所选日期区间没有行情。")
        if "cumulative_return" in frame:
            frame["cumulative_return"] = frame["close"] / frame["close"].iloc[0] - 1
        for column in ("open", "high", "low", "close", "preclose", "volume"):
            if column in frame:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
        return frame
