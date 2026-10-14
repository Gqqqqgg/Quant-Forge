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

## 实时计算接口

接口按模块组织：`backend/api/stocks.py` 提供原始股票列表，`backend/api/factor_engine/` 接收计算参数并返回响应。计算业务位于 `backend/factor_engine/`：`adjustment.py` 计算复权、`returns.py` 计算收益率、`indicators.py` 计算指标；`adjustment.py` 的 `get_adjusted_k_line()` 读取原始数据并复权，`returns.py` 的 `get_returns()` 和 `indicators.py` 的 `get_indicators()` 分别组织收益率和指标计算、日期截取及累计收益基准；图表通过 `get_indicators(include_prices=True)` 合并价格。`api/factor_engine/request.py` 定义 `FactorEngineRequest`，`api/factor_engine/response.py` 定义 `FactorEngineResponse`，并直接调用各模块函数、转换 HTTP 错误及组装响应。计算模块不依赖 API，计算不落盘。

- `GET /api/stocks?source=baostock`：列出 `STOCK_NAMES` 中已有原始日线的股票。
- `GET /api/indexs?source=baostock`：通过 `get_indexs()` 列出已有原始日线的配置指数，列表字段为 `indexs`。
- `POST /api/factor_engine/adjustment`：返回不复权原始日线，或计算前复权、后复权日线。
- `POST /api/factor_engine/returns`：计算每日与累计收益率。
- `POST /api/factor_engine/indicators`：计算指定窗口的均线、收益率波动率和平均成交量。
- `POST /api/factor_engine/charts`：一次返回图表所需的价格、成交量、收益率和指标。
- `GET /api/stocks/{symbol}/charts`：支持同名查询参数，`windows` 可重复传入。

POST 请求示例：

```json
{
  "source": "baostock",
  "symbol": "sh.600519",
  "start_date": "2025-01-01",
  "end_date": "2026-10-13",
  "adjust_type": "hfq",
  "windows": [5, 20, 60]
}
```

数据源默认 `tushare`，现阶段 BaoStock 测试需显式传入 `baostock`。日期可省略，省略时使用已有历史区间。`adjust_type` 支持 `none`（不复权）、`qfq`（前复权）和 `hfq`（后复权），默认 `hfq`；指标窗口支持 2 至 250 的整数，空列表表示不计算窗口指标。

`adjustment.py` 的 `get_raw_k_line()` 读取指定区间的原始 K 线。`adjust_type="none"` 同样返回原始价格，只读取日线文件，无需复权因子；收益率与指标基于原始价格计算，除权日可能出现价格跳变。

`api/stocks.py` 的 `INDEX_NAMES` 与 `STOCK_NAMES` 一样直接配置代码和名称：上证指数（`sh.000001`）、深证成指（`sz.399001`）、创业板指（`sz.399006`）、上证50（`sh.000016`）、中证500（`sh.000905`）和沪深300（`sh.000300`）。使用现有 `DataService.sync_daily_k_line(symbols=list(INDEX_NAMES), ...)` 同步日线后，`get_indexs()`（`GET /api/indexs`）列出这些指数并返回 `asset_type="index"`；`get_stocks()` 只返回股票。指数通过现有图表接口计算均线、收益率和波动率，必须使用 `adjust_type="none"`，无需股票复权因子。

接口只读取 `{source}/row/k_line/<股票代码>.parquet` 和 `{source}/row/adjust_factor/<股票代码>.parquet`，无需 `calculated` 数据目录，不联网同步。复权价格乘以对应累计因子，首个行情日前必须存在有效因子。先使用截至结束日期的历史数据计算指标，再截取请求区间，保证滚动窗口预热和每日收益率连续；累计收益率以请求区间首日收盘价为基准。前复权使用本地因子当前基准。

指标列为 `maN`、`volatilityN` 和 `volume_maN`；波动率为每日收益率样本标准差（`ddof=1`），不年化。窗口不足或成交量缺失时对应窗口留空，JSON 返回 `null`。计算结果仅返回给调用方，不落盘。已有计算文件不再被读取。

## 测试

计算算法用例位于 `tests/factor_engine/`，使用模拟行情，不请求数据源或修改本地行情。在 `backend/` 执行：

```powershell
uv run --group dev pytest tests/factor_engine
```
