"""Thin AkShare adapter for raw stock, ETF, and index data."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError
import time
from typing import Any

from data.providers.types import DailyPayload


class AkShareProvider:
    name = "akshare"

    def __init__(self) -> None:
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("AkShare is not installed. Install it before running this task.") from exc
        self.ak = ak

    def fetch_daily(
        self,
        start_date: str,
        end_date: str,
        asset_type: str = "stock",
        limit: int | None = None,
        workers: int = 10,
        timeout: float = 30,
        retries: int = 3,
        delay: float = 0.5,
        backoff: float = 2.0,
        batch_size: int = 10,
        batch_interval: float = 5.0,
    ):
        """Yield one result per instrument so callers can persist incrementally."""
        if asset_type == "stock":
            instruments = self.ak.stock_info_a_code_name()
        elif asset_type == "etf":
            instruments = self.ak.fund_etf_spot_em()
        elif asset_type == "index":
            instruments = self.ak.stock_zh_index_spot_em(symbol="\u6caa\u6df1\u91cd\u8981\u6307\u6570")
        else:
            raise ValueError(f"Unsupported asset type: {asset_type}")

        if workers <= 0:
            raise ValueError("workers must be greater than zero")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if retries < 0:
            raise ValueError("retries must not be negative")
        if delay < 0 or backoff < 0:
            raise ValueError("delay and backoff must not be negative")
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        if batch_interval < 0:
            raise ValueError("batch_interval must not be negative")

        code_column = self._column(instruments, "code", "\u4ee3\u7801", "\u8bc1\u5238\u4ee3\u7801")
        symbols = instruments[code_column].astype(str).tolist()
        if limit is not None:
            if limit <= 0:
                raise ValueError("limit must be greater than zero")
            symbols = symbols[:limit]
        total = len(symbols)
        print(f"starting {total} instruments, workers={workers}, timeout={timeout}s", flush=True)

        executor = ThreadPoolExecutor(max_workers=min(workers, batch_size))
        try:
            for batch_start in range(0, total, batch_size):
                batch = symbols[batch_start : batch_start + batch_size]
                futures = []
                for offset, symbol in enumerate(batch):
                    index = batch_start + offset + 1
                    print(f"[{index}/{total}] request {symbol}", flush=True)
                    future = executor.submit(
                        self._fetch_symbol_with_retry,
                        symbol,
                        start_date,
                        end_date,
                        asset_type,
                        retries,
                        delay,
                        backoff,
                        timeout,
                    )
                    futures.append((symbol, index, future))
                for symbol, index, future in futures:
                    yield self._result(symbol, index, total, future, timeout, asset_type)
                if batch_start + batch_size < total and batch_interval:
                    print(f"batch complete; sleeping {batch_interval}s", flush=True)
                    time.sleep(batch_interval)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _fetch_symbol_with_retry(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        asset_type: str,
        retries: int,
        delay: float,
        backoff: float,
        timeout: float,
    ) -> Any:
        for attempt in range(retries + 1):
            if delay:
                time.sleep(delay if attempt == 0 else delay * (backoff**attempt))
            try:
                return self._fetch_symbol_daily(symbol, start_date, end_date, asset_type, timeout)
            except Exception:
                if attempt >= retries:
                    raise

    def _result(
        self, symbol: str, index: int, total: int, future: Any, timeout: float, asset_type: str
    ) -> DailyPayload:
        try:
            frame = future.result(timeout=timeout)
            if not frame.empty:
                frame.insert(0, "source_symbol", symbol)
                frame.insert(1, "asset_type", asset_type)
            print(f"[{index}/{total}] complete {symbol}, rows={len(frame)}", flush=True)
            return DailyPayload(symbol=symbol, payload=frame)
        except TimeoutError:
            print(f"[{index}/{total}] timeout {symbol} (>{timeout}s)", flush=True)
            return DailyPayload(symbol=symbol, payload=None, error=f"request timed out after {timeout}s")
        except Exception as exc:  # noqa: BLE001 - keep other symbols progressing.
            print(f"[{index}/{total}] failed {symbol}: {exc}", flush=True)
            return DailyPayload(symbol=symbol, payload=None, error=str(exc))

    def _fetch_symbol_daily(
        self, symbol: str, start_date: str, end_date: str, asset_type: str, timeout: float
    ) -> Any:
        start = start_date.replace("-", "")
        end = end_date.replace("-", "")
        if asset_type == "stock":
            return self.ak.stock_zh_a_hist(
                symbol=symbol, period="daily", start_date=start, end_date=end, adjust="", timeout=timeout
            )
        if asset_type == "etf":
            return self.ak.fund_etf_hist_em(
                symbol=symbol, period="daily", start_date=start, end_date=end, adjust=""
            )
        if asset_type == "index":
            return self.ak.stock_zh_index_daily_em(symbol=symbol, start_date=start, end_date=end)
        raise ValueError(f"Unsupported asset type: {asset_type}")

    @staticmethod
    def _column(frame: Any, *candidates: str) -> str:
        for candidate in candidates:
            if candidate in frame.columns:
                return candidate
        raise ValueError(f"Could not find an instrument code column in: {list(frame.columns)}")

    def fetch_corporate_actions(self, start_date: str, end_date: str) -> Any:
        raise NotImplementedError("AkShare corporate-action endpoint selection is not configured yet.")

