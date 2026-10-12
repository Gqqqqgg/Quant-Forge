"""增量同步原始行情数据的应用服务。"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from data.providers.akshare import AkShareProvider
from data.providers.baostock import BaoStockProvider
from data.storage.raw_store import RawStore


class DataService:
    def __init__(self) -> None:
        configured_root = os.getenv("A_STOCK_DATA_ROOT")
        root = Path(configured_root) if configured_root else Path.home() / ".a-stock-data"
        self.raw_store = RawStore(root)

    def sync_daily(
        self,
        source: str,
        asset_type: str,
        start_date: date,
        end_date: date,
        shard_size: int = 200,
        limit: int | None = None,
        workers: int = 1,
        timeout: float = 30,
        retries: int = 3,
        delay: float = 0.5,
        backoff: float = 2.0,
        batch_size: int = 10,
        batch_interval: float = 5.0,
        resume: bool = True,
    ) -> dict[str, Any]:
        if start_date > end_date:
            raise ValueError("开始日期必须早于或等于结束日期。")
        if shard_size <= 0:
            raise ValueError("分片大小必须大于 0。")

        provider, actual_source = self._provider_with_fallback(source)
        progress_path = self.raw_store.progress_path(
            actual_source,
            asset_type,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        progress = self.raw_store.load_progress(progress_path) if resume else {"completed_symbols": []}
        completed_symbols = set(progress.get("completed_symbols", []))
        summary: dict[str, Any] = {
            "source": actual_source,
            "asset_type": asset_type,
            "shard_size": shard_size,
            "success_count": 0,
            "failed_count": 0,
            "rows": 0,
            "shard_count": 0,
            "resumed_count": len(completed_symbols),
            "progress_file": str(progress_path),
            "failures": [],
        }
        batch = []
        for item in provider.fetch_daily(
            start_date.isoformat(),
            end_date.isoformat(),
            asset_type,
            limit=limit,
            workers=workers,
            timeout=timeout,
            retries=retries,
            delay=delay,
            backoff=backoff,
            batch_size=batch_size,
            batch_interval=batch_interval,
            skip_symbols=completed_symbols,
        ):
            if item.payload is None:
                summary["failed_count"] += 1
                summary["failures"].append({"symbol": item.symbol, "error": item.error})
                continue

            if getattr(item.payload, "empty", False):
                summary["failed_count"] += 1
                summary["failures"].append({"symbol": item.symbol, "error": "返回数据为空。"})
                continue

            batch.append(item)
            summary["success_count"] += 1
            if len(batch) >= shard_size:
                self._save_batch(summary, batch, actual_source, source, asset_type, start_date, end_date)
                completed_symbols.update(item.symbol for item in batch)
                self.raw_store.save_progress(progress_path, completed_symbols, "进行中")
                batch = []

        if batch:
            self._save_batch(summary, batch, actual_source, source, asset_type, start_date, end_date)
            completed_symbols.update(item.symbol for item in batch)
            self.raw_store.save_progress(progress_path, completed_symbols, "进行中")
        status = "已完成" if summary["failed_count"] == 0 else "已完成但存在失败标的"
        self.raw_store.save_progress(progress_path, completed_symbols, status)
        return summary

    def _save_batch(
        self,
        summary: dict[str, Any],
        batch: list[Any],
        actual_source: str,
        requested_source: str,
        asset_type: str,
        start_date: date,
        end_date: date,
    ) -> None:
        manifests = self.raw_store.save_batch(
            source=actual_source,
            asset_type=asset_type,
            dataset="daily",
            items=batch,
            request_start=start_date.isoformat(),
            request_end=end_date.isoformat(),
            requested_source=requested_source,
        )
        summary["shard_count"] += len(manifests)
        summary["rows"] += sum(manifest["row_count"] for manifest in manifests)

    def _provider_with_fallback(self, source: str):
        candidates = ("akshare", "baostock") if source == "auto" else (source,)
        errors = []
        for candidate in candidates:
            try:
                return self._provider(candidate), candidate
            except Exception as exc:  # noqa: BLE001 - 当前数据源初始化失败时尝试下一个数据源。
                errors.append(f"{candidate}: {exc}")
        raise RuntimeError("所有请求的数据源均初始化失败：" + "；".join(errors))

    @staticmethod
    def _provider(source: str):
        if source == "akshare":
            return AkShareProvider()
        if source == "baostock":
            return BaoStockProvider()
        raise ValueError(f"不支持的数据源：{source}")
