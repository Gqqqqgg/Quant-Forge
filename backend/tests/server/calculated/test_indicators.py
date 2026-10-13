import math

import pandas as pd
import pytest

from server.calculated.indicators import calculate_indicators


@pytest.fixture
def k_lines():
    return pd.DataFrame(
        {
            "code": ["sh.600036"] * 65,
            "trade_date": pd.bdate_range("2026-01-01", periods=65).strftime("%Y-%m-%d"),
            "close": [str(value) for value in range(1, 66)],
            "volume": ["100"] * 65,
            "adjust_type": ["hfq"] * 65,
        }
    )


def test_known_moving_averages_and_warmup(k_lines):
    original = k_lines.copy(deep=True)
    result = calculate_indicators(k_lines.iloc[::-1])
    for column, first, expected in (("ma5", 4, 3), ("ma20", 19, 10.5), ("ma60", 59, 30.5)):
        assert result[column].iloc[:first].isna().all()
        assert result[column].iloc[first] == expected
    assert result["ma5"].iloc[-1] == 63
    assert result["ma20"].iloc[-1] == 55.5
    assert result["ma60"].iloc[-1] == 35.5
    for window in (5, 20, 60):
        assert result[f"volume_ma{window}"].iloc[: window - 1].isna().all()
        assert result[f"volume_ma{window}"].iloc[window - 1 :].eq(100).all()
        assert result[f"volatility{window}"].iloc[:window].isna().all()
        assert pd.notna(result[f"volatility{window}"].iloc[window])
    pd.testing.assert_frame_equal(k_lines, original)


@pytest.mark.parametrize("window", [5, 20, 60])
def test_sample_volatility_is_not_annualized(k_lines, window):
    prices = [100.0]
    daily_returns = ([0.1, -0.1] * 30)[:window]
    for daily_return in daily_returns:
        prices.append(prices[-1] * (1 + daily_return))
    frame = k_lines.iloc[: window + 1].copy()
    frame["close"] = prices
    result = calculate_indicators(frame)
    mean = sum(daily_returns) / window
    expected = math.sqrt(sum((value - mean) ** 2 for value in daily_returns) / (window - 1))
    assert result[f"volatility{window}"].iloc[-1] == pytest.approx(expected)


def test_future_data_does_not_change_past_indicators(k_lines):
    prefix = calculate_indicators(k_lines.iloc[:60])
    changed = k_lines.copy()
    changed.loc[60:, "close"] = "1000000"
    changed.loc[60:, "volume"] = "999999"
    result = calculate_indicators(changed)
    pd.testing.assert_frame_equal(result.iloc[:60], prefix)


def test_stock_windows_are_isolated(k_lines):
    other = k_lines.iloc[:10].assign(code="sz.000333", close="1000", volume="0")
    result = calculate_indicators(pd.concat([k_lines, other]).sample(frac=1, random_state=42))
    selected = result.loc[result["code"] == "sz.000333"]
    assert selected["ma5"].iloc[:4].isna().all()
    assert selected["ma5"].iloc[4:].eq(1000).all()
    assert selected[["ma20", "ma60", "volatility20", "volume_ma20"]].isna().all().all()


@pytest.mark.parametrize("invalid", ["-1", "nan", "inf", "bad"])
def test_invalid_volume_is_rejected(k_lines, invalid):
    k_lines.loc[1, "volume"] = invalid
    with pytest.raises(ValueError, match="成交量"):
        calculate_indicators(k_lines)


@pytest.mark.parametrize("missing", ["", None])
@pytest.mark.parametrize("window", [5, 20, 60])
def test_missing_volume_leaves_window_empty(k_lines, missing, window):
    """缺失成交量不补零，只影响包含该记录的成交量窗口。"""
    k_lines.loc[20, "volume"] = missing
    result = calculate_indicators(k_lines)
    assert pd.isna(result["volume"].iloc[20])
    column = f"volume_ma{window}"
    if window <= 20:
        assert result[column].iloc[19] == 100
    assert result[column].iloc[20 : min(20 + window, len(result))].isna().all()
    if 20 + window < len(result):
        assert result[column].iloc[20 + window] == 100
    assert result["ma20"].iloc[20] == 11.5
