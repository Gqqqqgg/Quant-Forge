"""计算均线、收益率波动率和平均成交量。"""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from market_data.calculated.returns import Returns


class Indicators:
    """按股票计算基础技术指标，并保存到配置的数据目录。"""

    def __init__(self, root: Path | None = None) -> None:
        configured_root = os.getenv("A_STOCK_DATA_ROOT")
        self.root = (
            root if root is not None else (Path(configured_root) if configured_root else Path.home() / ".a-stock-data")
        )

    @staticmethod
    def calculate_indicators(k_lines: pd.DataFrame) -> pd.DataFrame:
        """使用当天及之前的数据计算指标，窗口不足时留空。"""
        if "volume" not in k_lines:
            raise ValueError("复权日线缺少字段：volume")
        prices = k_lines.copy()
        missing_volume = prices["volume"].isna() | prices["volume"].astype(str).str.strip().eq("")
        prices["volume"] = pd.to_numeric(prices["volume"], errors="coerce")
        valid_volume = prices["volume"].map(lambda value: pd.notna(value) and math.isfinite(value) and value >= 0)
        if not (valid_volume | missing_volume).all():
            raise ValueError("非空成交量必须是非负的有限数值。")
        output = Returns.calculate_returns(prices)
        prices = prices.sort_values(["code", "trade_date"]).reset_index(drop=True)
        # 收益率计算已经校验并规范化日期，以股票和交易日期对齐成交量。
        volumes = prices[["code", "trade_date", "volume"]].copy()
        volumes["trade_date"] = pd.to_datetime(volumes["trade_date"]).dt.strftime("%Y-%m-%d")
        output = output.merge(volumes, on=["code", "trade_date"], validate="one_to_one")
        groups = output.groupby("code")
        for window in (5, 20, 60):
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

    def calculate_saved_indicators(
        self,
        source: str = "tushare",
        symbols: list[str] | tuple[str, ...] | None = None,
    ) -> dict:
        """读取本地后复权日线，按股票完整计算并覆盖保存指标。"""
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
            frame = self.calculate_indicators(k_lines)
            frame["source"] = source
            frame["adjust_type"] = "hfq"
            frame["calculated_time"] = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
            path = source_root / "calculated" / "indicators" / f"{symbol}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = path.with_suffix(".parquet.tmp")
            frame.to_parquet(temporary_path, engine="pyarrow", index=False)
            temporary_path.replace(path)
            summary["stocks"].append({"code": symbol, "rows": len(frame), "path": str(path)})
        return summary
