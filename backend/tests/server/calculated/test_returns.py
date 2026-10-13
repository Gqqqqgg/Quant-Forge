import pandas as pd
import pytest

from server.calculated.returns import calculate_returns


@pytest.fixture
def k_lines():
    return pd.DataFrame(
        {
            "code": ["sh.600036"] * 3,
            "trade_date": ["2026-07-09", "2026-07-10", "2026-07-13"],
            "close": ["100", "110", "99"],
            "adjust_type": ["hfq"] * 3,
        }
    )


def test_daily_and_compounded_returns(k_lines):
    """先涨 10% 再跌 10%，累计为 -1%，不能将每日收益直接相加。"""
    original = k_lines.copy(deep=True)
    result = calculate_returns(k_lines.iloc[::-1])
    assert result["trade_date"].tolist() == k_lines["trade_date"].tolist()
    assert pd.isna(result["daily_return"].iloc[0])
    assert result["daily_return"].iloc[1:].tolist() == pytest.approx([0.1, -0.1])
    assert result["cumulative_return"].tolist() == pytest.approx([0, 0.1, -0.01])
    assert (1 + result["daily_return"].iloc[1:]).prod() - 1 == pytest.approx(-0.01)
    pd.testing.assert_frame_equal(k_lines, original)


def test_multiple_stocks_have_separate_baselines(k_lines):
    other = k_lines.assign(code="sz.000333", close=["50", "50", "100"])
    result = calculate_returns(pd.concat([other, k_lines]).sample(frac=1, random_state=42))
    assert result.groupby("code")["daily_return"].apply(lambda values: values.isna().sum()).tolist() == [1, 1]
    assert result.loc[result["code"] == "sz.000333", "cumulative_return"].tolist() == [0, 0, 1]
    assert result.loc[result["code"] == "sh.600036", "cumulative_return"].iloc[-1] == pytest.approx(-0.01)


def test_single_trading_day(k_lines):
    result = calculate_returns(k_lines.iloc[[0]])
    assert pd.isna(result["daily_return"].iloc[0])
    assert result["cumulative_return"].iloc[0] == 0


def test_returns_are_invariant_to_adjustment_scale(k_lines):
    qfq = k_lines.assign(close=pd.to_numeric(k_lines["close"]) / 5, adjust_type="qfq")
    hfq_result = calculate_returns(k_lines)
    qfq_result = calculate_returns(qfq)
    for column in ("daily_return", "cumulative_return"):
        pd.testing.assert_series_equal(hfq_result[column], qfq_result[column])


@pytest.mark.parametrize("invalid", ["0", "-1", "nan", "inf", "bad", None])
def test_invalid_close_is_rejected(k_lines, invalid):
    k_lines.loc[1, "close"] = invalid
    with pytest.raises(ValueError, match="复权收盘价"):
        calculate_returns(k_lines)


def test_duplicate_date_is_rejected(k_lines):
    with pytest.raises(ValueError, match="重复"):
        calculate_returns(pd.concat([k_lines, k_lines.iloc[[0]]]))


def test_invalid_date_is_rejected(k_lines):
    k_lines.loc[1, "trade_date"] = "2026-02-30"
    with pytest.raises(ValueError, match="日期"):
        calculate_returns(k_lines)
