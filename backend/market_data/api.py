"""行情同步工具接口，供开发时手工调用。"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any, Callable, Literal

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from market_data.providers.baostock import BaoStockProvider
from market_data.storage.metadata_store import MetadataStore
from market_data.storage.root_path import get_data_root
from market_data.storage.row_store import RowStore

router = APIRouter(prefix="/api/tools/market-data", tags=["行情工具（手工测试）"])


class SourceParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["baostock", "tushare"] = Field(default="tushare", description="免费测试请显式选择 baostock")


class TradeDatesParameters(SourceParameters):
    start_date: date | None = Field(default=None, description="不传时从 2000-01-01 开始")
    end_date: date | None = Field(default=None, description="不传时截至北京时间当年年末")

    @model_validator(mode="after")
    def validate_dates(self):
        start = self.start_date or date(2000, 1, 1)
        today = datetime.now(timezone(timedelta(hours=8))).date()
        end = self.end_date or date(today.year, 12, 31)
        if start > end:
            raise ValueError("开始日期不能晚于结束日期。")
        return self


class DailyParameters(TradeDatesParameters):
    start_date: date = Field(description="同步开始日期，包含当日")
    end_date: date = Field(description="同步结束日期，包含当日")
    symbols: list[Annotated[str, Field(pattern=r"^(sh|sz|bj)\.\d{6}$")]] | None = Field(
        default=None, min_length=1, description="如 sh.600519；不传则读取本地基础资料中的全量股票"
    )


def sync_trade_dates(
    source: str = "tushare",
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    """获取交易日历并按年份保存。"""
    today = datetime.now(timezone(timedelta(hours=8))).date()
    start_date = start_date or date(2000, 1, 1)
    end_date = end_date or date(today.year, 12, 31)
    if start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期。")

    provider = _provider(source)
    actual_source = provider.name

    frame = provider.fetch_trade_dates(start_date.isoformat(), end_date.isoformat())
    if frame.empty:
        raise RuntimeError(f"{actual_source} 返回的交易日历为空。")
    path = MetadataStore(get_data_root()).save_trade_dates(frame, actual_source)
    return {
        "source": actual_source,
        "dataset": "trade_dates",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "rows": len(frame),
        "path": str(path),
    }


def sync_stock_basic(source: str = "tushare") -> dict[str, Any]:
    """按数据源获取基础资料并保存为 Parquet 快照。"""
    provider = _provider(source)
    actual_source = provider.name
    snapshot_date = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    frame = provider.fetch_stock_basic()
    if frame.empty:
        raise RuntimeError(f"{actual_source} 返回的股票基础资料为空。")
    if "code" not in frame.columns:
        raise RuntimeError(f"{actual_source} 返回的股票基础资料缺少主键列：code。")
    path = MetadataStore(get_data_root()).save_asset_basic(frame, actual_source, "stock", "code", snapshot_date)
    return {"source": actual_source, "datasets": {"stock": len(frame)}, "paths": {"stock": str(path)}}


def sync_adjust_factor(
    source: str = "tushare",
    start_date: date | None = None,
    end_date: date | None = None,
    symbols: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """按股票列表逐只获取并保存复权因子。"""
    provider = _provider(source)
    actual_source = provider.name
    start_date, end_date, symbols = _prepare_sync_inputs(actual_source, start_date, end_date, symbols)

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
                    frame = provider.fetch_adjust_factor(symbol, start_date.isoformat(), end_date.isoformat(), **kwargs)
                except Exception as exc:  # noqa: BLE001
                    if not session_open or "未登录" not in str(exc):
                        raise
                    provider.disconnect()
                    provider.connect()
                    time.sleep(5)
                    frame = provider.fetch_adjust_factor(symbol, start_date.isoformat(), end_date.isoformat(), **kwargs)
                if frame is not None and not frame.empty:
                    RowStore(get_data_root()).save_adjust_factor(frame, actual_source)
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
    source: str = "tushare",
    start_date: date | None = None,
    end_date: date | None = None,
    symbols: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """按股票列表逐只获取并保存未复权日线行情。"""
    provider = _provider(source)
    actual_source = provider.name
    start_date, end_date, symbols = _prepare_sync_inputs(actual_source, start_date, end_date, symbols)

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
                    frame = provider.fetch_daily_k_line(symbol, start_date.isoformat(), end_date.isoformat(), **kwargs)
                except Exception as exc:  # noqa: BLE001
                    if not session_open or "未登录" not in str(exc):
                        raise
                    provider.disconnect()
                    provider.connect()
                    time.sleep(5)
                    frame = provider.fetch_daily_k_line(symbol, start_date.isoformat(), end_date.isoformat(), **kwargs)
                if frame is not None and not frame.empty:
                    RowStore(get_data_root()).save_daily_k_line(frame, actual_source)
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
        stock_path = MetadataStore(get_data_root()).root_path(source, "stock_basic") / "stock.parquet"
        if not stock_path.exists():
            raise RuntimeError(f"找不到股票基础资料：{stock_path}")
        stock_frame = pd.read_parquet(stock_path)
        stock_frame = stock_frame[stock_frame["type"].astype(str) == "1"]
        symbols = stock_frame["code"].dropna().astype(str).tolist()
    symbols = list(dict.fromkeys(symbols))

    return start_date, end_date, symbols


def _provider(source: str) -> BaoStockProvider:
    if source == "baostock":
        return BaoStockProvider()
    if source == "tushare":
        raise NotImplementedError("Tushare 同步接口尚未实现；免费流程测试请显式指定 source='baostock'。")
    raise ValueError(f"不支持的数据源：{source}")


def _sync(operation: Callable[..., dict[str, Any]], parameters: SourceParameters) -> dict[str, Any]:
    """执行同步，将工具使用中的常见错误转换为接口响应。"""
    try:
        return operation(**parameters.model_dump())
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sync/trade-dates", summary="同步交易日历")
def sync_trade_dates_tool(parameters: TradeDatesParameters) -> dict[str, Any]:
    return _sync(sync_trade_dates, parameters)


@router.post("/sync/stock-basic", summary="同步证券基础资料")
def sync_stock_basic_tool(parameters: SourceParameters) -> dict[str, Any]:
    return _sync(sync_stock_basic, parameters)


@router.post("/sync/adjust-factor", summary="同步复权因子")
def sync_adjust_factor_tool(parameters: DailyParameters) -> dict[str, Any]:
    return _sync(sync_adjust_factor, parameters)


@router.post("/sync/daily-k-line", summary="同步未复权日线")
def sync_daily_k_line_tool(parameters: DailyParameters) -> dict[str, Any]:
    return _sync(sync_daily_k_line, parameters)
