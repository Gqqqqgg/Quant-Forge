import argparse
from datetime import date

from fastapi import FastAPI

from data.service import DataService

app = FastAPI()


@app.get("/")
def hello_world():
    return {"message": "Hello, World!"}


def run_sync(args: argparse.Namespace) -> None:
    result = DataService().sync_daily(
        source=args.source,
        asset_type=args.asset_type,
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        shard_size=args.shard_size,
        limit=args.limit,
        workers=args.workers,
        timeout=args.timeout,
        retries=args.retries,
        delay=args.delay,
        backoff=args.backoff,
        batch_size=args.batch_size,
        batch_interval=args.batch_interval,
        resume=args.resume,
    )
    print(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Quant-Forge data commands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    sync_parser = subparsers.add_parser("sync", help="同步原始日线行情数据")
    sync_parser.add_argument("--source", choices=("auto", "akshare", "baostock"), default="auto")
    sync_parser.add_argument("--asset-type", choices=("stock", "etf", "index"), default="stock")
    sync_parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    sync_parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    sync_parser.add_argument("--shard-size", type=int, default=200, help="每个 Parquet 分片包含的标的数量。")
    sync_parser.add_argument("--limit", type=int, help="只同步前 N 个标的，用于测试。")
    sync_parser.add_argument("--workers", type=int, default=1, help="并发请求数；BaoStock 始终使用串行请求。")
    sync_parser.add_argument("--timeout", type=float, default=30, help="单个标的请求超时时间（秒）。")
    sync_parser.add_argument("--retries", type=int, default=3, help="请求失败后的重试次数。")
    sync_parser.add_argument("--delay", type=float, default=0.5, help="每次请求前的等待时间（秒）。")
    sync_parser.add_argument("--backoff", type=float, default=2.0, help="重试等待时间倍率。")
    sync_parser.add_argument("--batch-size", type=int, default=10, help="每批请求的标的数量。")
    sync_parser.add_argument("--batch-interval", type=float, default=5.0, help="两批请求之间的等待时间（秒）。")
    sync_parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否根据进度文件续跑，默认开启；使用 --no-resume 强制重新拉取。",
    )
    args = parser.parse_args()
    if args.command == "sync":
        run_sync(args)


if __name__ == "__main__":
    main()
