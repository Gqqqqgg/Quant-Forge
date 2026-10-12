"""BaoStock 日线数据适配器。"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd

from data.providers.types import DailyPayload


class BaoStockProvider:
    name = "baostock"

    def __init__(self) -> None:
        try:
            import baostock as bs
        except ImportError as exc:
            raise RuntimeError("未安装 BaoStock，请先安装依赖后再执行同步。") from exc
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
        skip_symbols: set[str] | None = None,
    ):
        """逐只股票串行获取日线数据，并在请求之间主动限速。"""
        if asset_type != "stock":
            raise NotImplementedError("BaoStock 当前只支持 stock 资产类型。")
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
        if limit is not None and limit <= 0:
            raise ValueError("标的数量限制必须大于 0。")

        if workers != 1:
            print("BaoStock 当前固定使用串行请求，已忽略并发数设置以降低限流风险。", flush=True)

        self.connect(retries=retries, delay=delay, backoff=backoff)
        try:
            stocks = self.bs.query_stock_basic()
            if stocks.error_code != "0":
                raise RuntimeError(f"获取 BaoStock 股票列表失败：{stocks.error_msg}")
            stock_frame = self._result_to_frame(stocks)
            if (
                "code" not in stock_frame.columns
                or "type" not in stock_frame.columns
                or "status" not in stock_frame.columns
            ):
                raise RuntimeError("BaoStock 股票列表中缺少 code、type 或 status 字段。")
            stock_frame["code"] = stock_frame["code"].astype(str)
            # 先按 BaoStock 的证券类型选择股票，保留退市股票。
            stock_frame = stock_frame[stock_frame["type"].astype(str) == "1"]
            # BaoStock 没有单独的 A/B 股字段，只能依据其公开代码规则排除 B 股。
            stock_frame = stock_frame[stock_frame["code"].map(self._is_a_share_code)]
            names = {}
            statuses = {}
            if "code_name" in stock_frame.columns:
                names = dict(zip(stock_frame["code"], stock_frame["code_name"].fillna("").astype(str)))
            if "status" in stock_frame.columns:
                statuses = dict(zip(stock_frame["code"], stock_frame["status"].fillna("").astype(str)))
            codes = stock_frame["code"].tolist()
            if limit is not None:
                codes = codes[:limit]
            if skip_symbols:
                codes = [code for code in codes if code not in skip_symbols]
            total = len(codes)
            print(f"开始同步 BaoStock，共 {total} 只 A 股，日期范围：{start_date} 至 {end_date}。", flush=True)
            for index, code in enumerate(codes, start=1):
                try:
                    if delay:
                        time.sleep(delay)
                    frame = self._query_symbol_with_retry(
                        code=code,
                        start_date=start_date,
                        end_date=end_date,
                        retries=retries,
                        delay=delay,
                        backoff=backoff,
                    )
                    frame.insert(1, "name", names.get(code, ""))
                    frame.insert(2, "listing_status", statuses.get(code, ""))
                    print(f"[{index}/{total}] 完成 {code}，行数：{len(frame)}。", flush=True)
                    yield DailyPayload(symbol=code, payload=frame)
                except Exception as exc:  # noqa: BLE001 - 单只股票失败不能中断全量同步。
                    message = f"股票 {code} 同步失败：{exc}"
                    print(f"[{index}/{total}] {message}", flush=True)
                    yield DailyPayload(symbol=code, payload=None, error=message)
                if index % batch_size == 0 and index < total and batch_interval:
                    print(f"已完成 {index} 只股票，等待 {batch_interval} 秒后继续。", flush=True)
                    time.sleep(batch_interval)
        finally:
            self.disconnect()

    def connect(self, retries: int = 3, delay: float = 0.5, backoff: float = 2.0) -> Any:
        """建立 BaoStock 匿名会话；这里的连接不代表账号认证。"""
        return self._connect_with_retry(retries, delay, backoff)

    def disconnect(self) -> None:
        """释放 BaoStock 匿名会话。"""
        self.bs.logout()

    def _connect_with_retry(self, retries: int, delay: float, backoff: float) -> Any:
        """建立连接失败时按退避策略重试。"""
        for attempt in range(retries + 1):
            if attempt:
                wait = delay * (backoff**attempt)
                if wait:
                    time.sleep(wait)
            connection = self.bs.login()
            if connection.error_code == "0":
                return connection
            if attempt >= retries:
                raise RuntimeError(f"BaoStock 连接初始化失败：{connection.error_msg}")
            print(
                f"BaoStock 连接初始化失败，将在第 {attempt + 1} 次重试：{connection.error_msg}",
                flush=True,
            )
        raise RuntimeError("BaoStock 连接初始化失败。")

    def _query_symbol_with_retry(
        self,
        code: str,
        start_date: str,
        end_date: str,
        retries: int,
        delay: float,
        backoff: float,
    ) -> pd.DataFrame:
        """获取一只股票的数据，失败后重试并逐步增加等待时间。"""
        last_error = "未知错误"
        for attempt in range(retries + 1):
            if attempt:
                wait = delay * (backoff**attempt)
                if wait:
                    time.sleep(wait)
            try:
                result = self.bs.query_history_k_data_plus(
                    code,
                    "code,date,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST",
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d",
                    adjustflag="3",
                )
                if result.error_code != "0":
                    raise RuntimeError(result.error_msg)
                frame = self._result_to_frame(result)
                if frame.empty:
                    return frame
                if delay:
                    time.sleep(delay)
                factors = self._query_adjust_factor_with_retry(
                    code=code,
                    end_date=end_date,
                    retries=retries,
                    delay=delay,
                    backoff=backoff,
                )
                frame = self._attach_adjust_factors(frame, factors)
                close = pd.to_numeric(frame["close"], errors="coerce")
                preclose = pd.to_numeric(frame["preclose"], errors="coerce")
                high = pd.to_numeric(frame["high"], errors="coerce")
                low = pd.to_numeric(frame["low"], errors="coerce")
                frame["change"] = close - preclose
                frame["amplitude"] = (high - low).div(preclose.where(preclose != 0)) * 100
                if "tradestatus" in frame.columns:
                    frame["is_suspended"] = frame["tradestatus"].astype(str).eq("0")
                frame["adjust_type"] = "raw"
                return frame
            except Exception as exc:  # noqa: BLE001 - 单只股票失败不能中断全量同步。
                last_error = str(exc)
                if attempt < retries:
                    if self._is_session_error(last_error):
                        print("BaoStock 会话已失效，正在重新建立连接后继续重试。", flush=True)
                        try:
                            self.connect(retries=retries, delay=delay, backoff=backoff)
                        except Exception as reconnect_exc:  # noqa: BLE001 - 连接失败时继续走统一重试流程。
                            last_error = f"{last_error}；重新连接失败：{reconnect_exc}"
                    print(
                        f"股票 {code} 第 {attempt + 1} 次请求失败，将重试：{last_error}",
                        flush=True,
                    )
        raise RuntimeError(last_error)

    def _query_adjust_factor_with_retry(
        self,
        code: str,
        end_date: str,
        retries: int,
        delay: float,
        backoff: float,
    ) -> pd.DataFrame:
        """获取从 A 股市场成立以来的复权因子，并按相同策略重试。"""
        last_error = "未知错误"
        for attempt in range(retries + 1):
            if attempt:
                wait = delay * (backoff**attempt)
                if wait:
                    time.sleep(wait)
            try:
                result = self.bs.query_adjust_factor(
                    code=code,
                    start_date="1990-01-01",
                    end_date=end_date,
                )
                if result.error_code != "0":
                    raise RuntimeError(result.error_msg)
                return self._result_to_frame(result)
            except Exception as exc:  # noqa: BLE001 - 复权因子查询失败时按策略重试。
                last_error = str(exc)
                if attempt < retries:
                    if self._is_session_error(last_error):
                        print("BaoStock 会话已失效，正在重新建立连接后继续重试。", flush=True)
                        try:
                            self.connect(retries=retries, delay=delay, backoff=backoff)
                        except Exception as reconnect_exc:  # noqa: BLE001 - 连接失败时继续走统一重试流程。
                            last_error = f"{last_error}；重新连接失败：{reconnect_exc}"
                    print(
                        f"股票 {code} 第 {attempt + 1} 次获取复权因子失败，将重试：{last_error}",
                        flush=True,
                    )
        raise RuntimeError(f"获取股票 {code} 复权因子失败：{last_error}")

    @staticmethod
    def _is_session_error(message: str) -> bool:
        """判断错误信息是否表示 BaoStock 会话已经失效。"""
        return "未登录" in message or "登录失效" in message or "会话失效" in message

    @staticmethod
    def _attach_adjust_factors(frame: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
        """将复权事件按生效日期向前匹配到每日行情。"""
        factor_columns = ["adjust_factor_date", "fore_adjust_factor", "back_adjust_factor", "adjust_factor"]
        if factors.empty:
            for column in factor_columns:
                frame[column] = pd.NA
            return frame

        factor_frame = factors.rename(
            columns={
                "dividOperateDate": "adjust_factor_date",
                "foreAdjustFactor": "fore_adjust_factor",
                "backAdjustFactor": "back_adjust_factor",
                "adjustFactor": "adjust_factor",
            }
        )
        factor_frame["adjust_factor_date"] = pd.to_datetime(factor_frame["adjust_factor_date"], errors="coerce")
        factor_frame = factor_frame.dropna(subset=["adjust_factor_date"]).sort_values("adjust_factor_date")
        daily = frame.copy()
        daily["_trade_date"] = pd.to_datetime(daily["date"], errors="coerce")
        daily = daily.sort_values("_trade_date")
        merged = pd.merge_asof(
            daily,
            factor_frame[factor_columns],
            left_on="_trade_date",
            right_on="adjust_factor_date",
            direction="backward",
        )
        return merged.drop(columns=["_trade_date"])

    @staticmethod
    def _result_to_frame(result: Any) -> pd.DataFrame:
        """合并 BaoStock 分页结果，避免依赖已移除的 DataFrame.append。"""
        frames = []
        if result.data:
            frames.append(pd.DataFrame(result.data, columns=result.fields))
            result.cur_row_num = len(result.data)
        while result.error_code == "0" and result.next():
            if result.data:
                frames.append(pd.DataFrame(result.data, columns=result.fields))
            result.cur_row_num = len(result.data)
        if result.error_code != "0":
            raise RuntimeError(f"读取 BaoStock 分页失败：{result.error_msg}")
        if not frames:
            return pd.DataFrame(columns=result.fields)
        return pd.concat(frames, ignore_index=True)

    def fetch_corporate_actions(self, start_date: str, end_date: str) -> Any:
        raise NotImplementedError("BaoStock 公司行动接口尚未配置。")

    @staticmethod
    def _is_a_share_code(code: str) -> bool:
        """依据 BaoStock 的代码规则排除沪深 B 股，不限制其他 A 股代码前缀。"""
        return not code.startswith(("sh.900", "sz.200"))
