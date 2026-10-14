"""动量策略的参数、展示信息和筛选入口。"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from strategies.momentum.definition import DEFAULT_PARAMETERS, STOCK_NAMES, StrategyDefinition, StrategyResult
from strategies.momentum.screening import run_screening


class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["baostock", "tushare"] = Field(title="数据源")
    start_date: date = Field(title="开始日期")
    end_date: date = Field(title="结束日期")
    adjust_type: Literal["none", "qfq", "hfq"] = Field(title="复权方式")
    benchmark_symbol: Literal["sh.000300", "sh.000001", "sz.399001", "sz.399006", "sh.000016", "sh.000905"] | None = (
        Field(title="基准指数")
    )
    min_return: float = Field(default=0, title="最低区间收益", allow_inf_nan=False, ge=-1)
    min_ma20_deviation: float = Field(default=0, title="最低 MA20 偏离", allow_inf_nan=False, ge=-1)


def run(values: dict | None = None, *, preview: bool = False) -> dict:
    """校验参数并执行筛选；预览模式仅返回展示信息与规则，不读取行情。"""
    parameters = Parameters.model_validate({**DEFAULT_PARAMETERS, **(values or {})})
    definition = StrategyDefinition.model_validate(
        {
            **parameters.model_dump(exclude={"min_return", "min_ma20_deviation"}),
            "name": "动量策略",
            "conditions": [
                {"metric": "range_return", "operator": "gte", "value": parameters.min_return},
                {"metric": "ma20_deviation", "operator": "gte", "value": parameters.min_ma20_deviation},
            ],
            "sort_by": "range_return",
            "sort_direction": "desc",
        }
    )
    if preview:
        return {
            "id": "momentum",
            "description": "筛选区间收益与 MA20 偏离达到设定下限的股票，按区间收益从高到低排列。",
            "definition": definition.model_dump(mode="json"),
            "universe": [
                {"symbol": symbol, "name": name, "industry": industry}
                for symbol, (name, industry) in STOCK_NAMES.items()
            ],
            "parameters": parameters.model_dump(mode="json"),
            "parameter_schema": Parameters.model_json_schema(),
        }
    return StrategyResult.model_validate(run_screening(definition)).model_dump(mode="json")
