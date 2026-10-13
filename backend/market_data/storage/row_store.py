"""将股票原始日线和复权因子保存为 Parquet。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd


class RowStore:
    """按数据源和行数据集保存 Parquet。"""

    def __init__(self, root: Path) -> None:
        self.root = root

    def save_adjust_factor(self, frame: pd.DataFrame, source: str) -> dict[str, Path]:
        """按股票代码保存复权因子，并按证券及生效日期去重。"""
        required = {"code", "dividOperateDate"}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"复权因子数据缺少字段：{', '.join(sorted(missing))}")

        output = frame.copy()
        output["source"] = source
        output["ingest_time"] = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
        dates = pd.to_datetime(output["dividOperateDate"], errors="coerce")
        output = output.loc[dates.notna()].copy()
        output["dividOperateDate"] = dates.loc[output.index].dt.strftime("%Y-%m-%d")

        paths: dict[str, Path] = {}
        dataset_root = self.root / source / "row" / "adjust_factor"
        for code, partition in output.groupby("code"):
            path = dataset_root / f"{code}.parquet"
            if path.exists():
                partition = pd.concat([pd.read_parquet(path), partition], ignore_index=True)
            partition = (
                partition.drop_duplicates(subset=["code", "dividOperateDate"], keep="last")
                .sort_values(["code", "dividOperateDate"])
                .reset_index(drop=True)
            )
            dataset_root.mkdir(parents=True, exist_ok=True)
            temporary_path = path.with_suffix(".parquet.tmp")
            partition.to_parquet(temporary_path, engine="pyarrow", index=False)
            temporary_path.replace(path)
            paths[str(code)] = path
        return paths

    def save_daily_k_line(self, frame: pd.DataFrame, source: str) -> dict[str, Path]:
        """按股票代码保存原始日线，并以 code/trade_date 去重。"""
        required = {"code", "trade_date", "open", "high", "low", "close"}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"日线行情数据缺少字段：{', '.join(sorted(missing))}")

        output = frame.copy()
        output["source"] = source
        output["ingest_time"] = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
        dates = pd.to_datetime(output["trade_date"], errors="coerce")
        output = output.loc[dates.notna()].copy()
        if output.empty:
            return {}
        output["trade_date"] = dates.loc[output.index].dt.strftime("%Y-%m-%d")

        paths: dict[str, Path] = {}
        dataset_root = self.root / source / "row" / "k_line"
        for code, partition in output.groupby("code"):
            path = dataset_root / f"{code}.parquet"
            if path.exists():
                partition = pd.concat([pd.read_parquet(path), partition], ignore_index=True)
            partition = (
                partition.drop_duplicates(subset=["code", "trade_date"], keep="last")
                .sort_values(["code", "trade_date"])
                .reset_index(drop=True)
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = path.with_suffix(".parquet.tmp")
            partition.to_parquet(temporary_path, engine="pyarrow", index=False)
            temporary_path.replace(path)
            paths[str(code)] = path
        return paths
