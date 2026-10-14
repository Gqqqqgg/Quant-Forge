"""启动 FastAPI 策略展示服务。"""

import argparse

import uvicorn
from fastapi import FastAPI

from strategies.api import router as strategies_router

app = FastAPI(title="Quant Forge", description="独立策略展示与参数预览")
app.include_router(strategies_router)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
