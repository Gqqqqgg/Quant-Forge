"""Persist raw provider responses as time-partitioned Parquet shards."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

import pandas as pd


class RawStore:
    supported_sources = frozenset({"akshare", "baostock"})
    supported_asset_types = frozenset({"stock", "etf", "index"})

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save_batch(
        self,
        source: str,
        asset_type: str,
        dataset: str,
        items: Iterable[Any],
        request_start: str,
        request_end: str,
        requested_source: str,
    ) -> list[dict[str, Any]]:
        self._validate(source, asset_type, dataset)
        frames = [item.payload for item in items if item.payload is not None and not item.payload.empty]
        if not frames:
            return []

        frame = pd.concat(frames, ignore_index=True)
        date_column = self._date_column(frame)
        if date_column:
            frame["_partition_date"] = pd.to_datetime(frame[date_column], errors="coerce")
            frame = frame.dropna(subset=["_partition_date"])
        else:
            frame["_partition_date"] = pd.Timestamp(request_start)

        manifests = []
        for year, year_frame in frame.groupby(frame["_partition_date"].dt.year):
            partition = self.root / source / asset_type / dataset / f"year={int(year)}"
            if request_start == request_end:
                partition = partition / f"trade_date={request_start}"
            partition.mkdir(parents=True, exist_ok=True)
            batch_id = uuid4().hex
            data_path = partition / f"part-{batch_id}.parquet"
            output = year_frame.drop(columns=["_partition_date"])
            output.to_parquet(data_path, index=False)
            manifest = {
                "batch_id": batch_id,
                "source": source,
                "requested_source": requested_source,
                "asset_type": asset_type,
                "dataset": dataset,
                "request_start": request_start,
                "request_end": request_end,
                "year": int(year),
                "row_count": len(output),
                "file_path": str(data_path),
                "file_hash": hashlib.sha256(data_path.read_bytes()).hexdigest(),
                "written_at": datetime.now(timezone.utc).isoformat(),
            }
            manifest_path = partition / f"part-{batch_id}.manifest.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            manifests.append({**manifest, "manifest_path": str(manifest_path)})
        return manifests

    @staticmethod
    def _date_column(frame: pd.DataFrame) -> str | None:
        for name in ("trade_date", "日期", "date", "Date"):
            if name in frame.columns:
                return name
        return None

    def _validate(self, source: str, asset_type: str, dataset: str) -> None:
        if source not in self.supported_sources:
            raise ValueError(f"Unsupported raw source: {source}")
        if asset_type not in self.supported_asset_types:
            raise ValueError(f"Unsupported raw asset type: {asset_type}")
        if not dataset:
            raise ValueError("dataset must not be empty")
