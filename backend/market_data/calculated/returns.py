"""基于复权收盘价计算每日收益率和累计收益率。"""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd


class Returns:
    """计算收益率，并按股票保存到配置的数据目录。"""

    def __init__(self, root: Path | None = None) -> None:
        configured_root = os.getenv("A_STOCK_DATA_ROOT")
        self.root = (
            root if root is not None else (Path(configured_root) if configured_root else Path.home() / ".a-stock-data")
        )

    @staticmethod
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

    def calculate_saved_returns(
        self,
        source: str = "tushare",
        symbols: list[str] | tuple[str, ...] | None = None,
    ) -> dict:
        """读取本地后复权日线，计算收益率并按股票完整覆盖保存。"""
        if source not in {"tushare", "baostock"}:
            raise ValueError(f"不支持的数据源：{source}")
        source_root = self.root / source
        k_line_root = source_root / "calculated" / "hfq_k_line"
        if symbols is None:
            symbols = sorted(path.stem for path in k_line_root.glob("*.parquet"))
        symbols = list(dict.fromkeys(symbols))
        if not symbols:
            raise ValueError(f"找不到需要计算的后复权日线：{k_line_root}")
        summary = {"source": source, "stocks": []}
        for symbol in symbols:
            k_lines = pd.read_parquet(k_line_root / f"{symbol}.parquet")
            if k_lines.empty or set(k_lines["code"]) != {symbol}:
                raise ValueError(f"{symbol} 的后复权日线为空或包含其他股票。")
            if "adjust_type" in k_lines and not k_lines["adjust_type"].eq("hfq").all():
                raise ValueError(f"{symbol} 的日线不是后复权数据。")
            frame = self.calculate_returns(k_lines)
            frame["source"] = source
            frame["adjust_type"] = "hfq"
            frame["calculated_time"] = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
            path = source_root / "calculated" / "returns" / f"{symbol}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = path.with_suffix(".parquet.tmp")
            frame.to_parquet(temporary_path, engine="pyarrow", index=False)
            temporary_path.replace(path)
            summary["stocks"].append({"code": symbol, "rows": len(frame), "path": str(path)})
        return summary
