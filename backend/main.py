"""启动策略展示与行情手工测试工具服务。"""

import argparse

import uvicorn
from fastapi import FastAPI

from market_data.api import router as market_data_router
from strategies.api import router as strategies_router

app = FastAPI(title="Quant Forge", description="独立策略展示、参数预览与行情手工测试工具")
app.include_router(strategies_router)
app.include_router(market_data_router)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
