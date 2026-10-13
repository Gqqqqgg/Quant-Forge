"""使用 BaoStock 累计因子计算前复权和后复权日线。"""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import pandas as pd


class Adjustment:
    """计算复权行情，并按股票保存到配置的数据目录。"""

    def __init__(self, root: Path | None = None) -> None:
        configured_root = os.getenv("A_STOCK_DATA_ROOT")
        self.root = (
            root if root is not None else (Path(configured_root) if configured_root else Path.home() / ".a-stock-data")
        )

    @staticmethod
    def calculate_adjusted_k_line(
        k_lines: pd.DataFrame,
        factors: pd.DataFrame,
        adjust_type: Literal["qfq", "hfq"],
    ) -> pd.DataFrame:
        """按股票匹配当天已生效的因子，返回新的复权行情表。"""
        factor_columns = {"qfq": "foreAdjustFactor", "hfq": "backAdjustFactor"}
        if adjust_type not in factor_columns:
            raise ValueError(f"不支持的复权类型：{adjust_type}")
        factor_column = factor_columns[adjust_type]
        for frame, required, label in (
            (k_lines, {"code", "trade_date", "open", "high", "low", "close"}, "原始日线"),
            (factors, {"code", "dividOperateDate", factor_column}, "复权因子"),
        ):
            missing = required.difference(frame.columns)
            if missing:
                raise ValueError(f"{label}缺少字段：{', '.join(sorted(missing))}")
            if frame["code"].isna().any():
                raise ValueError(f"{label}包含空股票代码。")

        output = k_lines.copy()
        events = factors[["code", "dividOperateDate", factor_column]].copy()
        output["trade_date"] = pd.to_datetime(output["trade_date"], errors="raise")
        events["dividOperateDate"] = pd.to_datetime(events["dividOperateDate"], errors="raise")
        if output["trade_date"].isna().any() or events["dividOperateDate"].isna().any():
            raise ValueError("日线或复权因子包含空日期。")
        if output.duplicated(["code", "trade_date"]).any():
            raise ValueError("原始日线包含重复的股票和交易日期。")
        if events.duplicated(["code", "dividOperateDate"]).any():
            raise ValueError("复权因子包含重复的股票和生效日期。")
        events[factor_column] = pd.to_numeric(events[factor_column], errors="raise")
        valid_factors = events[factor_column].map(lambda value: pd.notna(value) and math.isfinite(value) and value > 0)
        if not valid_factors.all():
            raise ValueError("复权因子必须是正的有限数值。")

        price_columns = [column for column in ("open", "high", "low", "close", "preclose") if column in output]
        for column in price_columns:
            output[column] = pd.to_numeric(output[column], errors="raise")
            if not output[column].map(lambda value: pd.notna(value) and math.isfinite(value)).all():
                raise ValueError(f"价格字段 {column} 包含空值或非有限数值。")

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
            raise ValueError(
                f"{first['code']} 在 {first['trade_date'].date()} 缺少已生效因子，请补齐起始日前的因子记录。"
            )
        for column in price_columns:
            output[column] = output[column] * output["price_factor"]
        output["trade_date"] = output["trade_date"].dt.strftime("%Y-%m-%d")
        output["factor_date"] = output["factor_date"].dt.strftime("%Y-%m-%d")
        output["adjust_type"] = adjust_type
        return output.sort_values(["code", "trade_date"]).reset_index(drop=True)

    def calculate_saved_k_lines(
        self,
        source: str = "tushare",
        symbols: list[str] | tuple[str, ...] | None = None,
    ) -> dict:
        """读取本地股票文件，计算两种复权日线并按股票完整覆盖保存。"""
        if source != "baostock":
            raise NotImplementedError(f"尚未实现 {source} 的复权因子转换。")
        source_root = self.root / source
        k_line_root = source_root / "row" / "k_line"
        if symbols is None:
            symbols = sorted(path.stem for path in k_line_root.glob("*.parquet"))
        symbols = list(dict.fromkeys(symbols))
        if not symbols:
            raise ValueError(f"找不到需要计算的股票：{k_line_root}")
        summary = {"source": source, "stocks": []}
        for symbol in symbols:
            k_lines = pd.read_parquet(k_line_root / f"{symbol}.parquet")
            factors = pd.read_parquet(source_root / "row" / "adjust_factor" / f"{symbol}.parquet")
            if k_lines.empty or set(k_lines["code"]) != {symbol}:
                raise ValueError(f"{symbol} 的原始日线为空或包含其他股票。")
            if set(factors["code"]) != {symbol}:
                raise ValueError(f"{symbol} 的因子文件为空或包含其他股票。")
            results = {mode: self.calculate_adjusted_k_line(k_lines, factors, mode) for mode in ("qfq", "hfq")}
            stock = {"code": symbol, "rows": len(k_lines)}
            for mode, frame in results.items():
                dataset = "qfq_k_line" if mode == "qfq" else "hfq_k_line"
                path = source_root / "calculated" / dataset / f"{symbol}.parquet"
                path.parent.mkdir(parents=True, exist_ok=True)
                frame["calculated_time"] = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                temporary_path = path.with_suffix(".parquet.tmp")
                frame.to_parquet(temporary_path, engine="pyarrow", index=False)
                temporary_path.replace(path)
                stock[mode] = str(path)
            summary["stocks"].append(stock)
        return summary
