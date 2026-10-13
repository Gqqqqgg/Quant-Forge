"""保存交易日历、证券基础资料等低频元数据。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

BEIJING_TIMEZONE = timezone(timedelta(hours=8))


class MetadataStore:
    """将元数据按数据集合并保存为数据根目录下的 Parquet 文件。"""

    def __init__(self, root: Path) -> None:
        self.root = root

    def save_trade_dates(self, frame: pd.DataFrame, source: str) -> Path:
        dataset_root = self.root_path(source, "trade_dates")
        output = frame.copy()
        output["source"] = source
        output["ingest_time"] = datetime.now(BEIJING_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        dates = pd.to_datetime(output["calendar_date"], errors="coerce")
        for year, partition in output.groupby(dates.dt.year):
            self._save_partition(dataset_root, partition, ["calendar_date"], f"{int(year)}.parquet")
        return dataset_root

    def save_asset_basic(
        self,
        frame: pd.DataFrame,
        source: str,
        asset_type: str,
        key: str,
        snapshot_date: str,
    ) -> Path:
        dataset_root = self.root_path(source, "stock_basic")
        output = frame.copy()
        output["source"] = source
        output["ingest_time"] = datetime.now(BEIJING_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        output, _ = self._save_partition(
            dataset_root,
            output,
            [key],
            f"{asset_type}_{snapshot_date}.parquet",
            merge_existing=False,
        )
        self._save_partition(dataset_root, output, [key], f"{asset_type}.parquet", merge_existing=False)
        return dataset_root / f"{asset_type}.parquet"

    @staticmethod
    def _save_partition(
        dataset_root: Path,
        frame: pd.DataFrame,
        keys: list[str],
        filename: str = "data.parquet",
        merge_existing: bool = True,
    ) -> tuple[pd.DataFrame, Path]:
        dataset_root.mkdir(parents=True, exist_ok=True)
        path = dataset_root / filename
        if merge_existing and path.exists():
            frame = pd.concat([pd.read_parquet(path), frame], ignore_index=True)
        frame = frame.drop_duplicates(subset=keys, keep="last").sort_values(keys).reset_index(drop=True)
        temporary_path = path.with_suffix(".parquet.tmp")
        frame.to_parquet(temporary_path, engine="pyarrow", index=False)
        temporary_path.replace(path)
        return frame, path

    def root_path(self, source: str, dataset: str) -> Path:
        """返回指定数据源和 metadata 数据集的根目录。"""
        return self.root / source / "metadata" / dataset
