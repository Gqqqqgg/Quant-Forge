from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Metric = Literal[
    "range_return", "max_drawdown", "volatility", "ma20_deviation", "ma60_deviation", "volume_ratio", "excess_return"
]


class StrategyCondition(BaseModel):
    metric: Metric
    operator: Literal["gte", "lte"]
    value: float = Field(allow_inf_nan=False)


class StrategyDefinition(BaseModel):
    name: str = Field(default="行情规则筛选", min_length=1)
    source: Literal["baostock", "tushare"] = "tushare"
    start_date: date
    end_date: date
    adjust_type: Literal["none", "qfq", "hfq"] = "hfq"
    benchmark_symbol: str | None = Field(default="sh.000300", pattern=r"^(sh|sz|bj)\.\d{6}$")
    conditions: list[StrategyCondition] = Field(default_factory=list, max_length=20)
    sort_by: Metric = "range_return"
    sort_direction: Literal["asc", "desc"] = "desc"

    @model_validator(mode="after")
    def validate_rules(self):
        if self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期。")
        if self.benchmark_symbol is None and (
            self.sort_by == "excess_return" or any(rule.metric == "excess_return" for rule in self.conditions)
        ):
            raise ValueError("超额收益筛选或排序需要选择基准指数。")
        return self


class ScreeningCheck(StrategyCondition):
    actual: float | None
    passed: bool


class ScreeningCandidate(BaseModel):
    symbol: str
    name: str
    industry: str
    start_date: date
    end_date: date
    rows: int
    metrics: dict[Metric, float | None]
    checks: list[ScreeningCheck]
    comparison_error: str | None


class ScreeningError(BaseModel):
    symbol: str
    name: str
    error: str


class StrategyResult(BaseModel):
    definition: StrategyDefinition
    total: int
    matched: int
    candidates: list[ScreeningCandidate]
    excluded: list[ScreeningCandidate]
    errors: list[ScreeningError]


DEFAULT_PARAMETERS = {
    "source": "baostock",
    "start_date": "2026-07-13",
    "end_date": "2026-10-13",
    "adjust_type": "hfq",
    "benchmark_symbol": "sh.000300",
}


STOCK_NAMES = {
    "sh.600519": ("贵州茅台", "白酒"),
    "sh.600036": ("招商银行", "银行"),
    "sz.000333": ("美的集团", "家电"),
    "sz.300750": ("宁德时代", "动力电池"),
    "sh.600900": ("长江电力", "水电"),
}


INDEX_NAMES = {
    "sh.000001": ("上证指数", "指数"),
    "sz.399001": ("深证成指", "指数"),
    "sz.399006": ("创业板指", "指数"),
    "sh.000016": ("上证50", "指数"),
    "sh.000905": ("中证500", "指数"),
    "sh.000300": ("沪深300", "指数"),
}

SECURITY_NAMES = STOCK_NAMES | INDEX_NAMES
