"""Tushare provider 基础封装。"""

from __future__ import annotations

import tushare as ts


class TushareProvider:
    """持有 Tushare SDK 客户端，具体数据接口按需扩展。"""

    name = "tushare"

    def __init__(self, token: str | None = None) -> None:
        self.sdk = ts
        self.client = ts.pro_api(token) if token else None
