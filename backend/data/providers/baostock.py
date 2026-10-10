"""Thin BaoStock adapter used as a stock-data fallback."""

from __future__ import annotations

from typing import Any

import pandas as pd

from data.providers.types import DailyPayload


class BaoStockProvider:
    name = "baostock"

    def __init__(self) -> None:
        try:
            import baostock as bs
        except ImportError as exc:
            raise RuntimeError("BaoStock is not installed. Install it before running this task.") from exc
        self.bs = bs

    def fetch_daily(
        self,
        start_date: str,
        end_date: str,
        asset_type: str = "stock",
        limit: int | None = None,
        workers: int = 1,
        timeout: float = 30,
        retries: int = 3,
        delay: float = 0.5,
        backoff: float = 2.0,
        batch_size: int = 10,
        batch_interval: float = 5.0,
    ):
        if asset_type != "stock":
            raise NotImplementedError("BaoStock fallback currently supports stock instruments only.")

        login = self.bs.login()
        if login.error_code != "0":
            raise RuntimeError(f"BaoStock login failed: {login.error_msg}")
        try:
            stocks = self.bs.query_stock_basic()
            if stocks.error_code != "0":
                raise RuntimeError(f"BaoStock stock list query failed: {stocks.error_msg}")
            codes = self._result_to_frame(stocks)["code"].astype(str).tolist()
            if limit is not None:
                codes = codes[:limit]
            for code in codes:
                try:
                    result = self.bs.query_history_k_data_plus(
                        code,
                        "code,date,open,high,low,close,preclose,volume,amount",
                        start_date=start_date,
                        end_date=end_date,
                        frequency="d",
                        adjustflag="3",
                    )
                    if result.error_code != "0":
                        yield DailyPayload(symbol=code, payload=None, error=result.error_msg)
                        continue
                    yield DailyPayload(symbol=code, payload=self._result_to_frame(result))
                except Exception as exc:  # noqa: BLE001 - keep other symbols progressing.
                    yield DailyPayload(symbol=code, payload=None, error=str(exc))
        finally:
            self.bs.logout()

    @staticmethod
    def _result_to_frame(result: Any) -> pd.DataFrame:
        """Convert BaoStock pages without its pandas<2.0 DataFrame.append call."""
        frames = []
        if result.data:
            frames.append(pd.DataFrame(result.data, columns=result.fields))
            result.cur_row_num = len(result.data)
        while result.error_code == "0" and result.next():
            if result.data:
                frames.append(pd.DataFrame(result.data, columns=result.fields))
            result.cur_row_num = len(result.data)
        if not frames:
            return pd.DataFrame(columns=result.fields)
        return pd.concat(frames, ignore_index=True)

    def fetch_corporate_actions(self, start_date: str, end_date: str) -> Any:
        raise NotImplementedError("BaoStock corporate-action endpoint selection is not configured yet.")
