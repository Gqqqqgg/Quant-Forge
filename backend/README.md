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

同步命令通过 `main.py` 的 `sync` 子命令执行。建议先用单个交易日测试：

```powershell
uv run python main.py sync --source akshare --asset-type stock --start-date 2026-10-09 --end-date 2026-10-09 --shard-size 200
```

首次测试建议限制标的数量：

```powershell
uv run python main.py sync --source akshare --asset-type stock --start-date 2026-10-09 --end-date 2026-10-09 --limit 5 --timeout 30
```

使用 BaoStock 拉取最近十年 A 股日线数据：

```powershell
uv run python main.py sync --source baostock --asset-type stock --start-date 2016-10-11 --end-date 2026-10-11 --shard-size 200 --workers 1 --delay 0.5 --batch-size 10 --batch-interval 5
```

参数说明：

- `--source`：`auto`、`akshare` 或 `baostock`，默认是 `auto`。
- `--asset-type`：`stock`、`etf` 或 `index`，默认是 `stock`。
- `--start-date`、`--end-date`：同步日期范围，格式为 `YYYY-MM-DD`。
- `--shard-size`：每个 Parquet 分片聚合的标的数量，默认 200。
- `--limit`：只同步前 N 个标的，用于测试。
- `--workers`：并发请求数，默认 1；BaoStock 始终使用串行请求，避免同一连接会话并发访问。
- `--timeout`：单个标的请求超时时间（秒），默认 30；BaoStock SDK 不提供硬超时，此参数只用于统一 provider 接口校验。
- `--retries`：请求失败后的重试次数，默认 3。
- `--delay`：每次请求前的等待时间（秒），默认 0.5。
- `--backoff`：重试等待时间倍率，默认 2；例如等待 0.5、1、2 秒。
- `--batch-size`：每批请求的标的数量，默认 10。
- `--batch-interval`：两批请求之间的等待时间（秒），默认 5；BaoStock 会实际执行该等待。
- `--resume` / `--no-resume`：是否读取进度文件续跑，默认开启；使用 `--no-resume` 强制重新拉取。

执行同步时，`main.py` 会直接调用 `DataService`；启动 Uvicorn 或导入 `main` 不会触发同步。

## 代码格式化

在当前目录执行：

```powershell
uv run --group dev isort .
uv run --group dev black .
```

数据 provider 按资产类型采集原始日线：AkShare 支持 `stock`、`etf` 和 `index`；BaoStock 当前只支持 `stock`。BaoStock 先按基础资料的证券类型字段筛选 `type=1` 的股票，再依据 BaoStock 的公开代码规则排除 `sh.900` 和 `sz.200` B 股，保留在市和退市 A 股；不限制其他 A 股代码前缀，采集范围以 BaoStock 实际返回的股票列表为准；再通过通用的 `connect()` 生命周期方法建立匿名会话，底层调用 BaoStock SDK 的 `bs.login()`；这里不涉及用户名、密码、Token 或 API Key。历史行情会把基础资料中的 `code_name` 写入 `name` 列，把基础资料中的 `status` 写入 `listing_status`，并请求开收高低、成交量额、复权标记、换手率、交易状态、涨跌幅和常用估值字段，同时计算 `change`、`amplitude`、`is_suspended` 和 `adjust_type`。同步还会调用 BaoStock 的 `query_adjust_factor()`，按复权事件生效日期关联 `fore_adjust_factor`、`back_adjust_factor` 和 `adjust_factor`。Parquet 行中还会写入 `source`、`ingest_time` 和 `schema_version`。涨跌停价、成交笔数和市值仍需要其他接口或数据源。对于查询日期晚于退市日期的股票，BaoStock 返回空行情是正常现象。随后使用串行请求，并在每只股票之间等待、失败后重试并退避；如果服务端返回“用户未登录”或会话失效，程序会先重新建立匿名连接，再重试当前请求。原始返回结果按 provider 和资产类型分别保存。

数据同步通过 `data.service.DataService` 直接调用。全量同步按标的逐个获取，按 `shard_size` 聚合后写入 Parquet 分片，不通过 HTTP 返回全市场数据，也不把所有标的合并到一个 DataFrame。分片用于控制内存、文件大小和中断时的数据损失范围，不用于控制请求频率。默认数据目录是系统用户目录下的 `.a-stock-data`，也可以用 `A_STOCK_DATA_ROOT` 覆盖。

只有返回非空 DataFrame 的标的才会写入。程序累计到 `shard_size` 个成功标的后写入一个分片；如果同步中途被中断，尚未达到 `shard_size` 的缓存批次不会写入。正常结束时会写入最后一个不足 `shard_size` 的批次。

进度文件保存在 `.a-stock-data/_progress/`，按数据源、资产类型和日期范围区分。进度在每个分片成功写入后更新；重新执行相同任务时会跳过已经完成的股票。失败的股票不会标记为完成，下一次续跑会再次尝试。

原始数据目录固定为：

```text
~/.a-stock-data/
  akshare/
    stock/daily/
    etf/daily/
    index/daily/
  baostock/
    stock/daily/
    etf/daily/
    index/daily/
```

分片路径示例：

```text
~/.a-stock-data/akshare/stock/daily/year=2026/trade_date=2026-10-10/part-<id>.parquet
```

