"""Application service for incremental raw market-data synchronization."""

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
        workers: int = 10,
        timeout: float = 30,
        retries: int = 3,
        delay: float = 0.5,
        backoff: float = 2.0,
        batch_size: int = 10,
        batch_interval: float = 5.0,
    ) -> dict[str, Any]:
        if start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date")
        if shard_size <= 0:
            raise ValueError("shard_size must be greater than zero")

        provider, actual_source = self._provider_with_fallback(source)
        summary: dict[str, Any] = {
            "source": actual_source,
            "asset_type": asset_type,
            "shard_size": shard_size,
            "success_count": 0,
            "failed_count": 0,
            "rows": 0,
            "shard_count": 0,
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
        ):
            if item.payload is None:
                summary["failed_count"] += 1
                summary["failures"].append({"symbol": item.symbol, "error": item.error})
                continue

            if getattr(item.payload, "empty", False):
                summary["failed_count"] += 1
                summary["failures"].append({"symbol": item.symbol, "error": "empty response"})
                continue

            batch.append(item)
            summary["success_count"] += 1
            if len(batch) >= shard_size:
                self._save_batch(summary, batch, actual_source, source, asset_type, start_date, end_date)
                batch = []

        if batch:
            self._save_batch(summary, batch, actual_source, source, asset_type, start_date, end_date)
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
            except Exception as exc:  # noqa: BLE001 - try the next configured provider.
                errors.append(f"{candidate}: {exc}")
        raise RuntimeError("All requested providers failed: " + "; ".join(errors))

    @staticmethod
    def _provider(source: str):
        if source == "akshare":
            return AkShareProvider()
        if source == "baostock":
            return BaoStockProvider()
        raise ValueError(f"Unsupported source: {source}")
