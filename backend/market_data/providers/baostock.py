"""BaoStock 元数据 provider。"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd


class BaoStockProvider:
    name = "baostock"

    def __init__(self) -> None:
        try:
            import baostock as bs
        except ImportError as exc:
            raise RuntimeError("未安装 BaoStock，请先安装依赖。") from exc
        self.bs = bs

    def fetch_trade_dates(self, start_date: str, end_date: str) -> pd.DataFrame:
        self.connect()
        try:
            result = self.bs.query_trade_dates(start_date=start_date, end_date=end_date)
            if result.error_code != "0":
                raise RuntimeError(f"BaoStock 交易日历请求失败：{result.error_msg}")
            return self._result_to_frame(result)
        finally:
            self.disconnect()

    def fetch_stock_basic(self) -> pd.DataFrame:
        self.connect()
        try:
            result = self.bs.query_stock_basic()
            if result.error_code != "0":
                raise RuntimeError(f"BaoStock 证券基础资料请求失败：{result.error_msg}")
            return self._result_to_frame(result)
        finally:
            self.disconnect()

    def fetch_adjust_factor(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        manage_session: bool = True,
    ) -> pd.DataFrame:
        """获取单只证券的复权事件和复权因子。"""
        if manage_session:
            self.connect()
        try:
            result = self.bs.query_adjust_factor(
                code=symbol,
                start_date=start_date,
                end_date=end_date,
            )
            if result.error_code != "0":
                raise RuntimeError(f"BaoStock 复权因子请求失败：{result.error_msg}")
            return self._result_to_frame(result)
        finally:
            if manage_session:
                self.disconnect()

    def fetch_daily_k_line(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjustflag: str = "3",
        manage_session: bool = True,
    ) -> pd.DataFrame:
        """获取单只证券的日线行情。``adjustflag=3`` 表示不复权。"""
        if manage_session:
            self.connect()
        try:
            fields = "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg"
            result = self.bs.query_history_k_data_plus(
                symbol,
                fields,
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag=adjustflag,
            )
            if result.error_code != "0":
                raise RuntimeError(f"BaoStock 日线行情请求失败：{result.error_msg}")
            frame = self._result_to_frame(result)
            if frame.empty:
                return frame
            return frame.rename(columns={"date": "trade_date"})
        finally:
            if manage_session:
                self.disconnect()

    def connect(self, retries: int = 3, delay: float = 0.5, backoff: float = 2.0) -> Any:
        for attempt in range(retries + 1):
            if attempt:
                time.sleep(delay * (backoff**attempt))
            connection = self.bs.login()
            if connection.error_code == "0":
                return connection
            if attempt >= retries:
                raise RuntimeError(f"BaoStock 登录失败：{connection.error_msg}")
        raise RuntimeError("BaoStock 登录失败。")

    def disconnect(self) -> None:
        self.bs.logout()

    @staticmethod
    def _result_to_frame(result: Any) -> pd.DataFrame:
        frames = []
        if result.data:
            frames.append(pd.DataFrame(result.data, columns=result.fields))
            result.cur_row_num = len(result.data)
        while result.error_code == "0" and result.next():
            if result.data:
                frames.append(pd.DataFrame(result.data, columns=result.fields))
            result.cur_row_num = len(result.data)
        if result.error_code != "0":
            raise RuntimeError(f"BaoStock 分页读取失败：{result.error_msg}")
        if not frames:
            return pd.DataFrame(columns=result.fields)
        return pd.concat(frames, ignore_index=True)
