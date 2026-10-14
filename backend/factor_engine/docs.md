# 因子类型与计算说明

本文记录当前代码中的因子分类、实现位置与计算口径。预留类别中的因子仅作为说明示例，不表示已经实现。

因子用于描述股票特征。本文只介绍 `factor_engine` 中已有的计算函数、公式和输入输出。

## 1. 类型总览

| 类型 | 目录 | 描述 | 当前实现或预留示例 |
| --- | --- | --- | --- |
| 价值 | [value/](value/) | 相对盈利、净资产等基本面，价格是否便宜 | 未实现；示例：PE、PB、盈利收益率 E/P |
| 质量 | [quality/](quality/) | 公司盈利能力和财务稳健程度 | 未实现；示例：ROE、负债率、盈利稳定性 |
| 成长 | [growth/](growth/) | 公司业务和盈利的增长情况 | 未实现；示例：营收增长率、利润增长率 |
| 动量 | [momentum/](momentum/) | 价格走势与相对表现 | 收益率、价格均线、相对基准收益 |
| 波动与风险 | [risk/](risk/) | 收益波动和历史下跌程度 | 波动率、最大回撤 |
| 规模 | [size/](size/) | 公司在市场上的体量 | 未实现；示例：总市值、流通市值 |
| 流动性与交易活跃度 | [liquidity/](liquidity/) | 成交活动及其变化 | 平均成交量 |

## 2. 公式中的约定

- `t`：当前记录对应的交易日期；上一条记录不一定是前一个自然日。
- `P_t`：所选复权口径下的收盘价；`V_t`：行情中的成交量。
- `s`：请求区间内实际存在数据的首个交易日。
- `N`：滚动窗口的记录数，由调用者传入；均线、波动率和平均成交量函数没有默认窗口，也没有额外设置 250 的上限。样本波动率至少需要 2 条有效收益。
- 收益、波动率、回撤以比例存储，例如 `0.05` 表示 5%；超额收益 `0.05` 表示跑赢基准 5 个百分点。
- 滚动窗口包含当前记录，只使用当前及之前的数据；不自动补齐缺失交易日。

## 3. 动量类

| 因子或指标 | 对应文件与函数 | 计算方式 | 输出 |
| --- | --- | --- | --- |
| 每日收益率 | [momentum/returns.py](momentum/returns.py)：`calculate_returns` | `r_t = P_t / P_(t-1) - 1`，按股票分别计算 | `daily_return` |
| 累计／区间收益率 | [momentum/returns.py](momentum/returns.py)：`calculate_returns`、`select_returns_date_range` | 原始计算以各股票首条记录为基准；单只股票请求区间截取后以区间首日重设基准：`R_t = P_t / P_s - 1` | `cumulative_return` |
| N 日价格均线 | [momentum/moving_average.py](momentum/moving_average.py)：`calculate_moving_average` | `MA_N(t) = 最近 N 条收盘价之和 / N` | 与输入索引对齐的均线 Series |
| 相对基准表现 | [momentum/relative_strength.py](momentum/relative_strength.py)：`calculate_relative_strength` | 按双方共同交易日对齐，分别计算区间收益；`超额收益 = 股票累计收益 - 基准累计收益` | `security_return`、`benchmark_return`、`excess_return` |

计算细节：

- 收益率计算要求 `code`、`trade_date`、`close`，按股票及日期排序；空数据、重复股票日期、无效日期及非正或非有限价格会报错。
- 每只股票原始历史的第一条每日收益为空，累计收益为 0。
- `get_returns` 先计算截至结束日期的历史每日收益，再截取请求区间。因此区间首日的每日收益可能引用区间之前的价格，但累计收益从区间首日重新计为 0。
- 均线不足 N 条有效价格时为空，输出单位与输入价格相同。
- 相对强弱每次比较一个证券和一个基准，仅保留共同交易日，没有共同日期时报错。双方首个共同交易日均归一到 100，输出还包括 `security_normalized`、`benchmark_normalized`。
- 当前“相对强弱”是与基准的收益比较，不是 RSI 指标。
- 当前区间收益由起止日期决定，尚未提供独立的固定 N 日滚动收益因子。

## 4. 波动与风险类

| 因子 | 对应文件与函数 | 计算方式 | 输出 |
| --- | --- | --- | --- |
| N 日滚动波动率 | [risk/volatility.py](risk/volatility.py)：`calculate_volatility` | 最近 N 条有效每日收益的样本标准差：`sqrt(Σ(r_i - 平均收益)^2 / (N - 1))` | 与输入索引对齐的波动率 Series |
| 最大回撤 | [risk/drawdown.py](risk/drawdown.py)：`calculate_max_drawdown` | 各股票截至当日的历史最高收盘价为 `H_t`；`最大回撤 = max(1 - P_t / H_t)` | 非负比例浮点数 |

计算细节：

- 波动率不年化，使用 `ddof=1`；窗口中不足 N 条有效收益率时为空。原始历史第一条收益为空，因此 N 条有效收益通常需要 N+1 条价格。
- 最大回撤只使用传入数据的收盘价，先排序后计算，不衡量日内最高价至最低价的跌幅。
- 最大回撤对传入的每只股票分别维护最高价，再返回全部记录中最大的回撤。

## 5. 流动性与交易活跃度类

| 因子或指标 | 对应文件与函数 | 计算方式 | 输出 |
| --- | --- | --- | --- |
| N 日平均成交量 | [liquidity/volume.py](liquidity/volume.py)：`calculate_average_volume` | `平均成交量_N(t) = 最近 N 条成交量之和 / N` | 与输入索引对齐的平均成交量 Series |

平均成交量保留输入成交量的单位。该函数直接对传入序列执行滚动平均，不负责字符串转换或非负值校验；调用者应提供已清洗的数值序列。窗口不足 N 条有效成交量时，平均成交量为空，缺失值不补零。

## 6. 模块组织与导入

计算代码按因子的研究用途放入分类目录，各目录的 `__init__.py` 仅保留中文包说明，不定义计算函数或重新导出模块。滚动序列函数不自动排序或按股票分组，调用者应传入单只股票按时间排序的序列。

从具体实现模块导入所需函数，例如：

```python
from factor_engine.momentum.relative_strength import calculate_relative_strength
from factor_engine.momentum.returns import calculate_returns, get_returns
from factor_engine.risk.drawdown import calculate_max_drawdown
```

### 因子函数与数据依赖

| 实现文件 | 函数 | 输入 | 返回结果／数据依赖 |
| --- | --- | --- | --- |
| [momentum/returns.py](momentum/returns.py) | `calculate_returns` | 含股票代码、日期、收盘价的 DataFrame | 按股票和日期排序的收益表；只计算传入数据 |
| [momentum/returns.py](momentum/returns.py) | `select_returns_date_range` | 已计算收益的行情表、开始日期 | 截取后的行情表，并重设区间累计收益；不读取文件 |
| [momentum/returns.py](momentum/returns.py) | `get_returns` | 股票代码、数据源、日期、复权方式、可选数据目录 | 调用行情模块读取本地数据后计算收益的便捷入口 |
| [momentum/moving_average.py](momentum/moving_average.py) | `calculate_moving_average` | 单只股票按时间排序的价格 Series、窗口 N | 与输入索引对齐的均线 Series；不读取文件 |
| [momentum/relative_strength.py](momentum/relative_strength.py) | `calculate_relative_strength` | 股票与基准各自的价格 DataFrame | 共同交易日上的收益比较表；不读取文件 |
| [risk/volatility.py](risk/volatility.py) | `calculate_volatility` | 单只股票按时间排序的每日收益 Series、窗口 N | 与输入索引对齐的滚动波动率 Series；不读取文件 |
| [risk/drawdown.py](risk/drawdown.py) | `calculate_max_drawdown` | 含股票代码、日期、收盘价的 DataFrame | 最大回撤浮点数；不读取文件 |
| [liquidity/volume.py](liquidity/volume.py) | `calculate_average_volume` | 单只股票按时间排序的成交量 Series、窗口 N | 与输入索引对齐的平均成交量 Series；不读取文件 |

单只股票的 20 日均线与 20 日收益率波动率计算示例：

```python
from factor_engine.momentum.moving_average import calculate_moving_average
from factor_engine.momentum.returns import calculate_returns
from factor_engine.risk.volatility import calculate_volatility

# k_lines 为已读取、采用统一复权口径的单只股票历史行情。
returns = calculate_returns(k_lines)
ma20 = calculate_moving_average(returns["close"], window=20)
volatility20 = calculate_volatility(returns["daily_return"], window=20)
```
