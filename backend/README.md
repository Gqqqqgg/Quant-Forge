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

`main.py` 仅提供 FastAPI 应用入口。数据同步通过 `data.service.DataService` 的服务方法调用。

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

metadata 同步通过 `data.service.DataService` 直接调用。默认数据目录是系统用户目录下的 `.a-stock-data`，也可以用 `A_STOCK_DATA_ROOT` 覆盖。

交易日历已经按年份保存到 `{source}/metadata/trade_dates/<年份>.parquet`。证券基础资料按数据类型保存到 `{source}/metadata/stock_basic/stock.parquet`、`index.parquet` 和 `fund.parquet`，并按同步日期保存快照。

复权事件通过对应 provider 的 `fetch_adjust_factor()` 获取，并由 `DataService.sync_adjust_factor()` 写入 `{source}/row/adjust_factor/<年份>.parquet`；使用 `code` 和 `dividOperateDate` 去重。

日线行情通过 `DataService.sync_daily_k_line()` 同步，按年份和股票分片写入 `{source}/row/k_line/<年份>/<code>.parquet`，按 `code` 和 `trade_date` 去重。

复权因子和原始日线均按股票列表逐只采集和保存，每次请求前等待 5 秒，重新登录后的重试请求也一样。日期是否齐全及开始日期是否晚于结束日期由 service 检查。每次运行都重新请求整个股票列表，不读写进度文件。

当前已支持交易日历、证券基础资料、复权因子和未复权日线行情同步。日线行情字段以 `code`、`trade_date`、OHLC 为核心，并保留成交量、成交额和换手率（数据源提供时）。

