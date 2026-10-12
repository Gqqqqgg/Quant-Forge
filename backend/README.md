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

## 执行数据同步

同步命令通过 `main.py` 执行，默认同步未复权日线行情。

例如先同步 10 只股票进行验证：

```powershell
cd backend
uv run python main.py --dataset k_line --source baostock --start-date 2024-01-01 --end-date 2024-12-31 --limit 10
```

去掉 `--limit` 后同步全部股票；复权因子同步使用 `--dataset adjust_factor`。

基础资料 metadata 已完成同步。BaoStock 的 `query_stock_basic()` 返回多种证券类型，`type` 包括股票、指数、其他、可转债和 ETF，统一写入 `stock.parquet`。

`main.py` 仅保留 FastAPI 应用入口；数据同步通过 `data.service.DataService` 的服务方法调用。

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

日线行情通过 `DataService.sync_daily_k_line()` 同步，按年份和股票分片写入 `{source}/row/k_line/<年份>/<code>.parquet`，按 `code` 和 `trade_date` 去重；命令行可使用 `--dataset k_line` 执行。

全量复权因子同步使用 `DataService.sync_adjust_factor()`：固定 2 个并行任务、请求启动间隔 1 秒，每 20 只股票批量落盘并等待 5 秒；进度按数据源保存在 `{root}/<source>/row/adjust_factor/progress.json`。

当前已支持交易日历、证券基础资料、复权因子和未复权日线行情同步。日线行情字段以 `code`、`trade_date`、OHLC 为核心，并保留成交量、成交额和换手率（数据源提供时）。

