"""Provider result types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DailyPayload:
    symbol: str
    payload: Any | None
    error: str | None = None
