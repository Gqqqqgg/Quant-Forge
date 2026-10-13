# 后端

## 启动

在仓库根目录执行：

```powershell
.\scripts\dev.ps1
```

也可以在当前目录直接执行：

```powershell
uv run uvicorn main:app --reload
```

## 数据同步

`main.py` 仅提供 FastAPI 应用入口。市场数据采集和存储位于 `market_data/`，同步通过 `market_data.service.DataService` 的服务方法调用。

数据源默认是 `tushare`，不支持 `auto` 或自动切换。目前 Tushare 同步接口尚未实现，默认调用会明确报错。现阶段使用免费的 BaoStock 测试时，必须显式传入 `source="baostock"`；日线和复权因子同步须指定 `start_date` 和 `end_date`。

Service 的两个同步方法接受 `symbols`，传入股票列表时无需先同步 metadata，不传时从 `stock.parquet` 读取全量股票。`row_store.py` 仅保留 `save_adjust_factor()` 和 `save_daily_k_line()` 两个保存方法，命名与 service 对应。保存格式沿用现有逻辑，重复运行按股票和日期去重；同步方法返回成功数、失败数、行数和失败详情。

基础资料 metadata 已完成同步。BaoStock 的 `query_stock_basic()` 返回多种证券类型，`type` 包括股票、指数、其他、可转债和 ETF，统一写入 `stock.parquet`。

## 代码格式化

在当前目录执行：

```powershell
uv run --group dev isort .
uv run --group dev black .
```

数据 provider 使用 BaoStock 获取基础资料 metadata。BaoStock 使用 `query_stock_basic()` 获取包含 ETF 的证券基础列表，并保留接口的原始字段。BaoStock provider 通过通用的 `connect()` 生命周期方法建立匿名会话，底层调用 BaoStock SDK 的 `bs.login()`；这里不涉及用户名、密码、Token 或 API Key。metadata 行中会写入 `source` 和北京时间格式的 `ingest_time`。

metadata 同步通过 `market_data.service.DataService` 直接调用。默认数据目录是系统用户目录下的 `.a-stock-data`，也可以用 `A_STOCK_DATA_ROOT` 覆盖。

交易日历已经按年份保存到 `{source}/metadata/trade_dates/<年份>.parquet`。证券基础资料按数据类型保存到 `{source}/metadata/stock_basic/stock.parquet`、`index.parquet` 和 `fund.parquet`，并按同步日期保存快照。

复权事件通过对应 provider 的 `fetch_adjust_factor()` 获取，并由 `DataService.sync_adjust_factor()` 写入 `{source}/row/adjust_factor/<股票代码>.parquet`；每只股票一个文件，使用 `code` 和 `dividOperateDate` 去重。

日线行情通过 `DataService.sync_daily_k_line()` 同步，写入 `{source}/row/k_line/<股票代码>.parquet`，每只股票一个文件，按 `code` 和 `trade_date` 去重。复权因子和日线均跨年份合并保存，重复同步更新同一文件。交易日历仍按年份保存。

复权因子和原始日线均按股票列表逐只采集和保存，每次请求前等待 5 秒，重新登录后的重试请求也一样。日期是否齐全及开始日期是否晚于结束日期由 service 检查。每次运行都重新请求整个股票列表，不读写进度文件。

当前已支持交易日历、证券基础资料、复权因子和未复权日线行情同步。日线行情字段以 `code`、`trade_date`、OHLC 为核心，并保留成交量、成交额和换手率（数据源提供时）。

## 复权计算

`market_data.calculated.adjustment.Adjustment` 负责计算前复权和后复权 K 线。使用配置的数据目录，调用 `Adjustment().calculate_saved_k_lines(source="baostock")` 处理本地全部股票，也可传入 `symbols` 列表。

`calculate_adjusted_k_line()` 接收原始日线、BaoStock 因子和 `qfq`／`hfq` 类型，返回新 DataFrame。每个交易日匹配同股票最近已生效的因子，前复权乘 `foreAdjustFactor`，后复权乘 `backAdjustFactor`，不再累乘。OHLC 和 `preclose` 使用同一当天因子；成交量、成交额及原始涨跌幅保留。结果附带 `factor_date`、`price_factor` 和 `adjust_type`，落盘时增加 `calculated_time`。

结果保存为 `{source}/calculated/qfq_k_line/<股票代码>.parquet` 和 `{source}/calculated/hfq_k_line/<股票代码>.parquet`。每次完整重算并覆盖对应计算文件，原始 K 线不改动。前复权因子以获取因子时的最新基准为准，发生新除权后需要更新历史因子并重算历史前复权。

因子必须覆盖首个交易日：需要包含起始日前最近一条已生效记录。缺失时明确报错，不用未来因子或 `1` 填充。

## 收益率计算

`market_data.calculated.returns.Returns` 基于复权收盘价计算每日及累计收益率，使用 `Returns().calculate_saved_returns(source="baostock")` 处理本地全部后复权股票，也可传入 `symbols` 列表。计算不请求数据源。

`calculate_returns()` 接收 DataFrame，按股票和日期排序，返回 `code`、`trade_date`、`close`、`daily_return`、`cumulative_return`，输入包含 `adjust_type` 时也会保留。每日收益率为当日收盘价除以上一条交易记录的收盘价减一；累计收益率为当日收盘价除以该股票输入数据的首日收盘价减一，等价于每日收益的复利累计。首日每日收益留空，累计收益为零。收益率采用小数表示，`0.1` 表示 `10%`。收盘价缺失、非正或日期重复时明确报错。

批量计算读取 `{source}/calculated/hfq_k_line/<股票代码>.parquet`，结果完整覆盖保存到 `{source}/calculated/returns/<股票代码>.parquet`，增加 `source`、`adjust_type` 和 `calculated_time`。原始和复权 K 线均不改动。

## 技术指标

`market_data.calculated.indicators.Indicators` 提供 `calculate_indicators()`，接收含股票代码、交易日期、复权收盘价和原始成交量的 DataFrame，计算 5、20、60 日三个窗口的均线、收益率波动率和平均成交量。列名为 `ma5/ma20/ma60`、`volatility5/volatility20/volatility60`、`volume_ma5/volume_ma20/volume_ma60`。每日和累计收益率复用 `Returns` 的计算逻辑，也包含在输出中。

均线基于后复权收盘价；波动率是窗口内有效每日收益率的样本标准差（`ddof=1`），不做年化；平均成交量基于原始成交量。窗口均包含当天，仅使用当天及之前的数据，不足窗口时留空。N 日均线和平均成交量从第 N 条交易记录开始有效；首日收益为空，因此 N 日波动率从第 N+1 条交易记录开始有效。

原始成交量为空时保留为缺失值，不补零；包含缺失值的平均成交量窗口留空，不影响价格均线和收益率波动率。负数、非有限数值或无法解析的非空成交量会报错。

调用 `Indicators().calculate_saved_indicators(source="baostock")` 处理本地全部后复权股票，也可传入 `symbols`。读取 `{source}/calculated/hfq_k_line/<股票代码>.parquet`，完整覆盖保存到 `{source}/calculated/indicators/<股票代码>.parquet`，不请求数据源或修改输入 K 线。

## 测试

计算模块用例位于 `tests/calculated/`，使用模拟行情和临时目录，不请求数据源或修改本地行情。在 `backend/` 执行：

```powershell
uv run --group dev pytest tests/calculated
```

