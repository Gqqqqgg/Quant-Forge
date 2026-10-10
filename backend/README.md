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

参数说明：

- `--source`：`auto`、`akshare` 或 `baostock`，默认是 `auto`。
- `--asset-type`：`stock`、`etf` 或 `index`，默认是 `stock`。
- `--start-date`、`--end-date`：同步日期范围，格式为 `YYYY-MM-DD`。
- `--shard-size`：每个 Parquet 分片聚合的标的数量，默认 200。
- `--limit`：只同步前 N 个标的，用于测试。
- `--workers`：并发请求数，默认 1；提高该值可能触发数据源限流。
- `--timeout`：单个标的请求超时时间（秒），默认 30。
- `--retries`：请求失败后的重试次数，默认 3。
- `--delay`：每次请求前的等待时间（秒），默认 0.5。
- `--backoff`：重试等待时间倍率，默认 2；例如等待 0.5、1、2 秒。
- `--batch-size`：每批并行请求的标的数量，默认 10。
- `--batch-interval`：两批请求之间的等待时间（秒），默认 5。

执行同步时，`main.py` 会直接调用 `DataService`；启动 Uvicorn 或导入 `main` 不会触发同步。

## 代码格式化

在当前目录执行：

```powershell
uv run --group dev isort .
uv run --group dev black .
```

数据 provider 按资产类型采集原始日线：AkShare 支持 `stock`、`etf` 和 `index`；BaoStock 当前只支持 `stock` 作为兜底。原始返回结果按 provider 和资产类型分别保存，暂不做统一字段或复权处理。

数据同步通过 `data.service.DataService` 直接调用。全量同步按标的逐个获取，按 `shard_size` 聚合后写入 Parquet 分片，不通过 HTTP 返回全市场数据，也不把所有标的合并到一个 DataFrame。默认数据目录是系统用户目录下的 `.a-stock-data`，也可以用 `A_STOCK_DATA_ROOT` 覆盖。

只有返回非空 DataFrame 的标的才会写入。程序累计到 `shard_size` 个成功标的后写入一个分片；如果同步中途被中断，尚未达到 `shard_size` 的缓存批次不会写入。正常结束时会写入最后一个不足 `shard_size` 的批次。

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

