"""统一解析行情数据的根目录。"""

import os
from pathlib import Path


def get_data_root() -> Path:
    """读取行情数据目录配置，默认使用用户目录下的 .a-stock-data。"""
    configured_root = os.getenv("A_STOCK_DATA_ROOT")
    return Path(configured_root) if configured_root else Path.home() / ".a-stock-data"
