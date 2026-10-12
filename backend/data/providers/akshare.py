"""AkShare 股票、ETF 和指数日线数据适配器。"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

from data.providers.types import DailyPayload


class AkShareProvider:
    name = "akshare"

    def __init__(self) -> None:
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("未安装 AkShare，请先安装依赖后再执行同步。") from exc
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
        skip_symbols: set[str] | None = None,
    ):
        """逐个返回标的数据，便于调用方增量落盘。"""
        if asset_type == "stock":
            instruments = self.ak.stock_info_a_code_name()
        elif asset_type == "etf":
            instruments = self.ak.fund_etf_spot_em()
        elif asset_type == "index":
            instruments = self.ak.stock_zh_index_spot_em(symbol="\u6caa\u6df1\u91cd\u8981\u6307\u6570")
        else:
            raise ValueError(f"不支持的资产类型：{asset_type}")

        if workers <= 0:
            raise ValueError("并发数必须大于 0。")
        if timeout <= 0:
            raise ValueError("单只股票超时时间必须大于 0。")
        if retries < 0:
            raise ValueError("重试次数不能小于 0。")
        if delay < 0 or backoff < 0:
            raise ValueError("请求间隔和退避倍率不能小于 0。")
        if batch_size <= 0:
            raise ValueError("批次大小必须大于 0。")
        if batch_interval < 0:
            raise ValueError("批次间隔不能小于 0。")

        code_column = self._column(instruments, "code", "\u4ee3\u7801", "\u8bc1\u5238\u4ee3\u7801")
        symbols = instruments[code_column].astype(str).tolist()
        if limit is not None:
            if limit <= 0:
                raise ValueError("标的数量限制必须大于 0。")
            symbols = symbols[:limit]
        if skip_symbols:
            symbols = [symbol for symbol in symbols if symbol not in skip_symbols]
        total = len(symbols)
        print(f"开始同步，共 {total} 个标的，并发数：{workers}，超时时间：{timeout} 秒。", flush=True)

        executor = ThreadPoolExecutor(max_workers=min(workers, batch_size))
        try:
            for batch_start in range(0, total, batch_size):
                batch = symbols[batch_start : batch_start + batch_size]
                futures = []
                for offset, symbol in enumerate(batch):
                    index = batch_start + offset + 1
                    print(f"[{index}/{total}] 请求 {symbol}。", flush=True)
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
                    print(f"本批次完成，等待 {batch_interval} 秒后继续。", flush=True)
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
            print(f"[{index}/{total}] 完成 {symbol}，行数：{len(frame)}。", flush=True)
            return DailyPayload(symbol=symbol, payload=frame)
        except TimeoutError:
            print(f"[{index}/{total}] {symbol} 请求超时（超过 {timeout} 秒）。", flush=True)
            return DailyPayload(symbol=symbol, payload=None, error=f"请求超时，超过 {timeout} 秒。")
        except Exception as exc:  # noqa: BLE001 - 单只股票失败不能中断全量同步。
            message = f"股票 {symbol} 同步失败：{exc}"
            print(f"[{index}/{total}] {message}", flush=True)
            return DailyPayload(symbol=symbol, payload=None, error=message)

    def _fetch_symbol_daily(self, symbol: str, start_date: str, end_date: str, asset_type: str, timeout: float) -> Any:
        start = start_date.replace("-", "")
        end = end_date.replace("-", "")
        if asset_type == "stock":
            return self.ak.stock_zh_a_hist(
                symbol=symbol, period="daily", start_date=start, end_date=end, adjust="", timeout=timeout
            )
        if asset_type == "etf":
            return self.ak.fund_etf_hist_em(symbol=symbol, period="daily", start_date=start, end_date=end, adjust="")
        if asset_type == "index":
            return self.ak.stock_zh_index_daily_em(symbol=symbol, start_date=start, end_date=end)
        raise ValueError(f"不支持的资产类型：{asset_type}")

    @staticmethod
    def _column(frame: Any, *candidates: str) -> str:
        for candidate in candidates:
            if candidate in frame.columns:
                return candidate
        raise ValueError(f"未找到标的代码字段，当前字段为：{list(frame.columns)}")

    def fetch_corporate_actions(self, start_date: str, end_date: str) -> Any:
        raise NotImplementedError("AkShare 公司行动接口尚未配置。")
