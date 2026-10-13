"""同步股票基础资料、交易日历、复权因子和原始日线。"""

from __future__ import annotations

import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from data.providers.baostock import BaoStockProvider
from data.storage.metadata_store import MetadataStore
from data.storage.row_store import RowStore


class DataService:
    def __init__(self, root: Path | None = None) -> None:
        configured_root = os.getenv("A_STOCK_DATA_ROOT")
        root = (
            root if root is not None else (Path(configured_root) if configured_root else Path.home() / ".a-stock-data")
        )
        self.metadata_store = MetadataStore(root)
        self.row_store = RowStore(root)

    def sync_trade_dates(
        self,
        source: str = "tushare",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """获取交易日历并按年份保存。"""
        today = datetime.now(timezone(timedelta(hours=8))).date()
        start_date = start_date or date(2000, 1, 1)
        end_date = end_date or date(today.year, 12, 31)

        provider = self._provider(source)
        actual_source = provider.name

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

    def sync_stock_basic(self, source: str = "tushare") -> dict[str, Any]:
        """按数据源获取基础资料并保存为 Parquet 快照。"""
        provider = self._provider(source)
        actual_source = provider.name
        snapshot_date = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        frame = provider.fetch_stock_basic()
        if frame.empty:
            raise RuntimeError(f"{actual_source} 返回的股票基础资料为空。")
        if "code" not in frame.columns:
            raise RuntimeError(f"{actual_source} 返回的股票基础资料缺少主键列：code。")
        path = self.metadata_store.save_asset_basic(frame, actual_source, "stock", "code", snapshot_date)
        return {"source": actual_source, "datasets": {"stock": len(frame)}, "paths": {"stock": str(path)}}

    def sync_adjust_factor(
        self,
        source: str = "tushare",
        start_date: date | None = None,
        end_date: date | None = None,
        symbols: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        """按股票列表逐只获取并保存复权因子。"""
        provider = self._provider(source)
        actual_source = provider.name
        start_date, end_date, symbols = self._prepare_sync_inputs(actual_source, start_date, end_date, symbols)

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
        session_open = actual_source == "baostock"
        if session_open:
            provider.connect()
        try:
            for symbol in symbols:
                try:
                    kwargs = {"manage_session": False} if session_open else {}
                    try:
                        time.sleep(5)
                        frame = provider.fetch_adjust_factor(
                            symbol, start_date.isoformat(), end_date.isoformat(), **kwargs
                        )
                    except Exception as exc:  # noqa: BLE001
                        if not session_open or "未登录" not in str(exc):
                            raise
                        provider.disconnect()
                        provider.connect()
                        time.sleep(5)
                        frame = provider.fetch_adjust_factor(
                            symbol, start_date.isoformat(), end_date.isoformat(), **kwargs
                        )
                    if frame is not None and not frame.empty:
                        self.row_store.save_adjust_factor(frame, actual_source)
                        summary["rows"] += len(frame)
                    summary["success_count"] += 1
                except Exception as exc:  # noqa: BLE001
                    summary["failed_count"] += 1
                    summary["failures"].append({"symbol": symbol, "error": str(exc)})
        finally:
            if session_open:
                provider.disconnect()
        return summary

    def sync_daily_k_line(
        self,
        source: str = "tushare",
        start_date: date | None = None,
        end_date: date | None = None,
        symbols: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        """按股票列表逐只获取并保存未复权日线行情。"""
        provider = self._provider(source)
        actual_source = provider.name
        start_date, end_date, symbols = self._prepare_sync_inputs(actual_source, start_date, end_date, symbols)

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
        session_open = actual_source == "baostock"
        if session_open:
            provider.connect()
        try:
            for symbol in symbols:
                try:
                    kwargs = {"manage_session": False} if session_open else {}
                    try:
                        time.sleep(5)
                        frame = provider.fetch_daily_k_line(
                            symbol, start_date.isoformat(), end_date.isoformat(), **kwargs
                        )
                    except Exception as exc:  # noqa: BLE001
                        if not session_open or "未登录" not in str(exc):
                            raise
                        provider.disconnect()
                        provider.connect()
                        time.sleep(5)
                        frame = provider.fetch_daily_k_line(
                            symbol, start_date.isoformat(), end_date.isoformat(), **kwargs
                        )
                    if frame is not None and not frame.empty:
                        self.row_store.save_daily_k_line(frame, actual_source)
                        summary["rows"] += len(frame)
                    summary["success_count"] += 1
                except Exception as exc:  # noqa: BLE001
                    summary["failed_count"] += 1
                    summary["failures"].append({"symbol": symbol, "error": str(exc)})
        finally:
            if session_open:
                provider.disconnect()
        return summary

    def _prepare_sync_inputs(
        self,
        source: str,
        start_date: date | None,
        end_date: date | None,
        symbols: list[str] | tuple[str, ...] | None,
    ) -> tuple[date, date, list[str]]:
        """校验日期，并读取或整理去重后的股票列表。"""
        if start_date is None or end_date is None:
            raise ValueError("请指定开始日期和结束日期。")
        if start_date > end_date:
            raise ValueError("开始日期不能晚于结束日期。")

        if symbols is None:
            stock_path = self.metadata_store.root_path(source, "stock_basic") / "stock.parquet"
            if not stock_path.exists():
                raise RuntimeError(f"找不到股票基础资料：{stock_path}")
            stock_frame = pd.read_parquet(stock_path)
            stock_frame = stock_frame[stock_frame["type"].astype(str) == "1"]
            symbols = stock_frame["code"].dropna().astype(str).tolist()
        symbols = list(dict.fromkeys(symbols))

        return start_date, end_date, symbols

    @staticmethod
    def _provider(source: str) -> BaoStockProvider:
        if source == "baostock":
            return BaoStockProvider()
        if source == "tushare":
            raise NotImplementedError("Tushare 同步接口尚未实现；免费流程测试请显式指定 source='baostock'。")
        raise ValueError(f"不支持的数据源：{source}")
