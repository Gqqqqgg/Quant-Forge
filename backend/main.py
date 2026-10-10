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
    )
    print(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Quant-Forge data commands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    sync_parser = subparsers.add_parser("sync", help="Synchronize raw daily market data")
    sync_parser.add_argument("--source", choices=("auto", "akshare", "baostock"), default="auto")
    sync_parser.add_argument("--asset-type", choices=("stock", "etf", "index"), default="stock")
    sync_parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    sync_parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    sync_parser.add_argument("--shard-size", type=int, default=200)
    sync_parser.add_argument("--limit", type=int, help="Only sync the first N instruments (for testing).")
    sync_parser.add_argument("--workers", type=int, default=10, help="Concurrent instrument requests.")
    sync_parser.add_argument("--timeout", type=float, default=30, help="Timeout per instrument request in seconds.")
    sync_parser.add_argument("--retries", type=int, default=3, help="Retries after a failed request.")
    sync_parser.add_argument("--delay", type=float, default=0.5, help="Delay before each request in seconds.")
    sync_parser.add_argument("--backoff", type=float, default=2.0, help="Retry delay multiplier.")
    sync_parser.add_argument("--batch-size", type=int, default=10, help="Instruments per parallel batch.")
    sync_parser.add_argument("--batch-interval", type=float, default=5.0, help="Seconds between batches.")
    args = parser.parse_args()
    if args.command == "sync":
        run_sync(args)


if __name__ == "__main__":
    main()
