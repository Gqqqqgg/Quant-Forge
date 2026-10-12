"""AkShare 元数据 provider。"""

from __future__ import annotations

from datetime import date

import pandas as pd


class AkShareProvider:
    name = "akshare"

    def __init__(self) -> None:
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("未安装 AkShare，请先安装依赖。") from exc
        self.ak = ak

    def fetch_trade_dates(self, start_date: str, end_date: str) -> pd.DataFrame:
        frame = self.ak.tool_trade_date_hist_sina()
        if frame.empty or "trade_date" not in frame.columns:
            return pd.DataFrame(columns=["calendar_date"])

        raw_dates = frame["trade_date"]
        parsed_dates = pd.to_datetime(raw_dates, errors="coerce")
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        output = pd.DataFrame({"calendar_date": raw_dates})
        mask = parsed_dates.notna() & parsed_dates.dt.date.between(start, end)
        return output.loc[mask].reset_index(drop=True)

    def fetch_stock_basic(self) -> pd.DataFrame:
        """获取当前 A 股股票代码和名称列表。"""
        return self.ak.stock_info_a_code_name()

    def fetch_index_basic(self) -> pd.DataFrame:
        """获取 AkShare 原始指数列表。"""
        return self.ak.index_stock_info()

    def fetch_fund_basic(self) -> pd.DataFrame:
        """获取 AkShare 原始基金列表。"""
        return self.ak.fund_name_em()

    def fetch_adjust_factor(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取 AkShare 的前复权和后复权因子。"""
        start = start_date.replace("-", "")
        end = end_date.replace("-", "")
        qfq = self.ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start,
            end_date=end,
            adjust="qfq-factor",
        )
        hfq = self.ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start,
            end_date=end,
            adjust="hfq-factor",
        )

        qfq_frame = self._normalize_factor_frame(qfq, "qfq_factor", "qfq_adjust")
        hfq_frame = self._normalize_factor_frame(hfq, "hfq_factor", "hfq_adjust")
        if qfq_frame.empty and hfq_frame.empty:
            return pd.DataFrame(
                columns=[
                    "code",
                    "dividOperateDate",
                    "foreAdjustFactor",
                    "backAdjustFactor",
                    "qfq_adjust",
                    "hfq_adjust",
                ]
            )

        if qfq_frame.empty:
            output = hfq_frame
        elif hfq_frame.empty:
            output = qfq_frame
        else:
            output = pd.merge(qfq_frame, hfq_frame, on="dividOperateDate", how="outer")
        output.insert(0, "code", symbol)
        return output.sort_values("dividOperateDate").reset_index(drop=True)

    @staticmethod
    def _normalize_factor_frame(frame: pd.DataFrame, factor_column: str, output_column: str) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["dividOperateDate", factor_column, output_column])
        date_column = "日期" if "日期" in frame.columns else "date"
        if date_column not in frame.columns or factor_column not in frame.columns:
            return pd.DataFrame(columns=["dividOperateDate", factor_column, output_column])
        output = frame[[date_column, factor_column]].copy()
        output = output.rename(columns={date_column: "dividOperateDate"})
        if "adjust" in frame.columns:
            output[output_column] = frame["adjust"]
        else:
            output[output_column] = pd.NA
        return output
