import argparse
from datetime import date

from fastapi import FastAPI

from data.service import DataService

app = FastAPI()


@app.get("/")
def hello_world():
    return {"message": "Hello, World!"}


def fetch_adjust_factors(
    source: str = "baostock",
    start_date: date = date(2000, 1, 1),
    end_date: date | None = None,
    limit: int | None = None,
):
    """手动同步股票复权因子。"""
    return DataService().sync_adjust_factor(
        source=source,
        start_date=start_date,
        end_date=end_date or date.today(),
        limit=limit,
    )


def fetch_daily_k_lines(
    source: str = "baostock",
    start_date: date = date(2000, 1, 1),
    end_date: date | None = None,
    limit: int | None = None,
):
    """手动同步股票未复权日线行情。"""
    return DataService().sync_daily_k_line(
        source=source,
        start_date=start_date,
        end_date=end_date or date.today(),
        limit=limit,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Quant-Forge 数据同步脚本")
    parser.add_argument(
        "--dataset",
        choices=("k_line", "adjust_factor"),
        default="k_line",
        help="同步数据集，默认同步未复权日线行情",
    )
    parser.add_argument("--source", choices=("auto", "baostock"), default="baostock")
    parser.add_argument("--start-date", default="2015-01-01", help="开始日期，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", help="结束日期，格式 YYYY-MM-DD；默认今天")
    parser.add_argument("--limit", type=int, help="同步股票数量；不传则同步全部股票")
    args = parser.parse_args()
    fetch = fetch_adjust_factors if args.dataset == "adjust_factor" else fetch_daily_k_lines
    result = fetch(
        source=args.source,
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date) if args.end_date else None,
        limit=args.limit,
    )
    print(result)


if __name__ == "__main__":
    main()
