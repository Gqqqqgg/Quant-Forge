"""元数据同步服务。"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from data.providers.akshare import AkShareProvider
from data.providers.baostock import BaoStockProvider
from data.storage.metadata_store import MetadataStore
from data.storage.row_store import RowStore


# BaoStock 全量复权因子同步参数。保持较低并行度，避免触发服务端限流。
ADJUST_FACTOR_WORKERS = 2
ADJUST_FACTOR_REQUEST_INTERVAL = 1.0
ADJUST_FACTOR_BATCH_SIZE = 20
ADJUST_FACTOR_BATCH_INTERVAL = 5.0
BEIJING_TIMEZONE = timezone(timedelta(hours=8))


class DataService:
    def __init__(self) -> None:
        configured_root = os.getenv("A_STOCK_DATA_ROOT")
        root = Path(configured_root) if configured_root else Path.home() / ".a-stock-data"
        self.metadata_store = MetadataStore(root)
        self.row_store = RowStore(root)

    def sync_trade_dates(
        self,
        source: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """获取交易日历并按年份保存。"""
        today = datetime.now(timezone(timedelta(hours=8))).date()
        start_date = start_date or date(2000, 1, 1)
        end_date = end_date or date(today.year, 12, 31)

        if source in {"auto", "baostock"}:
            actual_source = "baostock" if source == "auto" else source
            provider = BaoStockProvider()
        elif source == "akshare":
            actual_source = source
            provider = AkShareProvider()
        else:
            raise ValueError(f"不支持的数据源：{source}")

        frame = provider.fetch_trade_dates(start_date.isoformat(), end_date.isoformat())
        if frame.empty:
            raise RuntimeError(f"{actual_source} 返回的交易日历为空。")
        path = self.metadata_store.save_trade_dates(frame, actual_source)
        return {
            "source": actual_source,
            "dataset": "trade_dates",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "rows": len(frame),
            "path": str(path),
        }

    def sync_stock_basic(self, source: str) -> dict[str, Any]:
        """按数据源获取基础资料并保存为 Parquet 快照。"""
        actual_source = "baostock" if source == "auto" else source
        if actual_source == "baostock":
            provider = BaoStockProvider()
            datasets = [("stock", provider.fetch_stock_basic, "code")]
        elif actual_source == "akshare":
            provider = AkShareProvider()
            datasets = [
                ("stock", provider.fetch_stock_basic, "code"),
                ("index", provider.fetch_index_basic, "index_code"),
                ("fund", provider.fetch_fund_basic, "基金代码"),
            ]
        else:
            raise ValueError(f"不支持的数据源：{source}")

        snapshot_date = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        rows: dict[str, int] = {}
        paths: dict[str, str] = {}
        for asset_type, fetch, key in datasets:
            # 每个数据集独立获取并落盘，便于定位具体失败的数据源。
            frame = fetch()
            if frame.empty:
                raise RuntimeError(f"{actual_source} 返回的 {asset_type} 列表为空。")
            if key not in frame.columns:
                raise RuntimeError(f"{actual_source} 返回的 {asset_type} 列表缺少主键列：{key}。")
            path = self.metadata_store.save_asset_basic(frame, actual_source, asset_type, key, snapshot_date)
            rows[asset_type] = len(frame)
            paths[asset_type] = str(path)

        return {"source": actual_source, "datasets": rows, "paths": paths}

    def sync_adjust_factor(
        self,
        source: str,
        start_date: date,
        end_date: date,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """按数据源并行同步股票复权因子，并按批次落盘。"""
        if source in {"auto", "baostock"}:
            actual_source = "baostock" if source == "auto" else source
            provider = BaoStockProvider()
            stock_path = self.metadata_store.root_path("baostock", "stock_basic") / "data.parquet"
            if not stock_path.exists():
                raise RuntimeError(f"找不到 {actual_source} 股票基础资料：{stock_path}")
            stock_frame = pd.read_parquet(stock_path)
            stock_frame = stock_frame[stock_frame["type"].astype(str) == "1"]
            symbols = stock_frame["code"].dropna().astype(str).drop_duplicates().tolist()
        elif source == "akshare":
            actual_source = source
            provider = AkShareProvider()
            stock_path = self.metadata_store.root_path("akshare", "stock_basic") / "stock.parquet"
            if not stock_path.exists():
                raise RuntimeError(f"找不到 {actual_source} 股票基础资料：{stock_path}")
            stock_frame = pd.read_parquet(stock_path)
            symbols = stock_frame["code"].dropna().astype(str).str.zfill(6).drop_duplicates().tolist()
        else:
            raise ValueError(f"不支持的数据源：{source}")
        if limit is not None:
            symbols = symbols[:limit]

        progress_path = (
            self.row_store.root
            / actual_source
            / "row"
            / "adjust_factor"
            / "progress.json"
        )
        progress = self._load_adjust_factor_progress(progress_path)
        request_range = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
        if (
            progress.get("start_date") != request_range["start_date"]
            or progress.get("end_date") != request_range["end_date"]
        ):
            progress = {**request_range, "completed_symbols": [], "failures": []}
        completed = set(progress.get("completed_symbols", []))
        symbols = [symbol for symbol in symbols if symbol not in completed]

        request_lock = threading.Lock()
        next_request_time = [0.0]
        summary: dict[str, Any] = {
            "source": actual_source,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total": len(symbols),
            "success_count": 0,
            "failed_count": 0,
            "rows": 0,
            "failures": [],
        }

        def fetch_batch(batch: list[str]) -> list[tuple[str, pd.DataFrame | None, str | None]]:
            worker_provider = type(provider)()
            manage_session = actual_source == "baostock"
            if manage_session:
                worker_provider.connect()
            results = []
            try:
                for symbol in batch:
                    with request_lock:
                        wait = next_request_time[0] - time.monotonic()
                        if wait > 0:
                            time.sleep(wait)
                        next_request_time[0] = time.monotonic() + ADJUST_FACTOR_REQUEST_INTERVAL
                    try:
                        kwargs = {"manage_session": False} if manage_session else {}
                        frame = worker_provider.fetch_adjust_factor(
                            symbol,
                            start_date.isoformat(),
                            end_date.isoformat(),
                            **kwargs,
                        )
                        results.append((symbol, frame, None))
                    except Exception as exc:  # noqa: BLE001
                        results.append((symbol, None, str(exc)))
            finally:
                if manage_session:
                    worker_provider.disconnect()
            return results

        pending_frames: list[pd.DataFrame] = []
        batches = [symbols[index : index + ADJUST_FACTOR_BATCH_SIZE] for index in range(0, len(symbols), ADJUST_FACTOR_BATCH_SIZE)]
        worker_count = 1 if actual_source == "baostock" else ADJUST_FACTOR_WORKERS
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(fetch_batch, batch) for batch in batches]
            for batch_index, future in enumerate(as_completed(futures), start=1):
                for symbol, frame, error in future.result():
                    if error:
                        summary["failed_count"] += 1
                        summary["failures"].append({"symbol": symbol, "error": error})
                        continue
                    completed.add(symbol)
                    summary["success_count"] += 1
                    if frame is not None and not frame.empty:
                        pending_frames.append(frame)
                        summary["rows"] += len(frame)
                if pending_frames:
                    combined = pd.concat(pending_frames, ignore_index=True)
                    self.row_store.save_adjust_factors(combined, actual_source)
                    pending_frames = []
                progress["completed_symbols"] = sorted(completed)
                progress.update(request_range)
                progress["last_updated"] = datetime.now(BEIJING_TIMEZONE).isoformat()
                progress["failures"] = summary["failures"]
                self._save_adjust_factor_progress(progress_path, progress)
                if batch_index < len(batches):
                    time.sleep(ADJUST_FACTOR_BATCH_INTERVAL)

        return summary

    @staticmethod
    def _load_adjust_factor_progress(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"completed_symbols": [], "failures": []}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"completed_symbols": [], "failures": []}

    @staticmethod
    def _save_adjust_factor_progress(path: Path, progress: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(".json.tmp")
        temporary_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary_path.replace(path)
