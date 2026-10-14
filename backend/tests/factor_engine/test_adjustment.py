import pandas as pd
import pytest

from factor_engine.adjustment import calculate_adjusted_k_line


@pytest.fixture
def frames():
    k_lines = pd.DataFrame(
        {
            "code": ["sh.600036"] * 3,
            "trade_date": ["2026-07-09", "2026-07-10", "2026-07-13"],
            "open": ["40", "39", "40"],
            "high": ["41", "40", "41"],
            "low": ["39", "38", "39"],
            "close": ["40", "39", "40"],
            "preclose": ["40", "39", "39"],
            "volume": ["100", "200", "300"],
            "amount": ["4000", "7800", "12000"],
        }
    )
    factors = pd.DataFrame(
        {
            "code": ["sh.600036"] * 2,
            "dividOperateDate": ["2026-01-16", "2026-07-10"],
            "foreAdjustFactor": ["0.973369", "1.000000"],
            "backAdjustFactor": ["5.589333", "5.742256"],
        }
    )
    return k_lines, factors


@pytest.mark.parametrize("mode,column", [("qfq", "foreAdjustFactor"), ("hfq", "backAdjustFactor")])
def test_effective_date_and_price_fields(frames, mode, column):
    k_lines, factors = frames
    original = k_lines.copy(deep=True)
    result = calculate_adjusted_k_line(k_lines, factors, mode)
    expected = [float(factors[column].iloc[0]), float(factors[column].iloc[1]), float(factors[column].iloc[1])]
    assert result["price_factor"].tolist() == expected
    for field in ("open", "high", "low", "close", "preclose"):
        assert result[field].tolist() == pytest.approx(pd.to_numeric(k_lines[field]) * expected)
    for field in ("volume", "amount"):
        pd.testing.assert_series_equal(result[field], k_lines[field])
    pd.testing.assert_frame_equal(k_lines, original)


def test_missing_initial_factor_is_not_filled_from_future(frames):
    k_lines, factors = frames
    with pytest.raises(ValueError, match="缺少已生效因子"):
        calculate_adjusted_k_line(k_lines, factors.iloc[[1]], "qfq")


def test_multiple_stocks_do_not_share_factors(frames):
    k_lines, factors = frames
    other_k = k_lines.assign(code="sz.000333")
    other_f = factors.assign(code="sz.000333", foreAdjustFactor="0.5")
    result = calculate_adjusted_k_line(pd.concat([other_k, k_lines]), pd.concat([factors, other_f]), "qfq")
    assert result.loc[result["code"] == "sz.000333", "price_factor"].tolist() == [0.5] * 3


@pytest.mark.parametrize("invalid", ["0", "nan", "inf", "-1"])
def test_invalid_factor_is_rejected(frames, invalid):
    k_lines, factors = frames
    factors.loc[0, "foreAdjustFactor"] = invalid
    with pytest.raises(ValueError):
        calculate_adjusted_k_line(k_lines, factors, "qfq")


@pytest.mark.parametrize("mode,expected", [("qfq", [5.0, 5.0]), ("hfq", [10.0, 10.0])])
def test_split_removes_artificial_price_drop(mode, expected):
    """一股拆为两股后，复权收盘价应连续，而不是出现 50% 的跌幅。"""
    k_lines = pd.DataFrame(
        {
            "code": ["sh.600036"] * 2,
            "trade_date": ["2026-07-09", "2026-07-10"],
            "open": ["10", "5"],
            "high": ["10", "5"],
            "low": ["10", "5"],
            "close": ["10", "5"],
        }
    )
    factors = pd.DataFrame(
        {
            "code": ["sh.600036"] * 2,
            "dividOperateDate": ["2026-01-01", "2026-07-10"],
            "foreAdjustFactor": ["0.5", "1"],
            "backAdjustFactor": ["1", "2"],
        }
    )
    result = calculate_adjusted_k_line(k_lines, factors, mode)
    assert result["close"].tolist() == expected
    assert result["close"].pct_change().iloc[1] == 0


def test_unsorted_inputs_and_weekend_event(frames):
    """输入可乱序；非交易日生效的因子从后续首个交易日起使用。"""
    k_lines, factors = frames
    factors.loc[1, "dividOperateDate"] = "2026-07-11"
    result = calculate_adjusted_k_line(k_lines.iloc[::-1], factors.iloc[::-1], "qfq")
    assert result["trade_date"].tolist() == ["2026-07-09", "2026-07-10", "2026-07-13"]
    assert result["price_factor"].tolist() == [0.973369, 0.973369, 1.0]
    assert result["factor_date"].tolist() == ["2026-01-16", "2026-01-16", "2026-07-11"]


@pytest.mark.parametrize("duplicate", ["k_lines", "factors"])
def test_duplicate_dates_are_rejected(frames, duplicate):
    k_lines, factors = frames
    if duplicate == "k_lines":
        k_lines = pd.concat([k_lines, k_lines.iloc[[0]]])
    else:
        factors = pd.concat([factors, factors.iloc[[0]]])
    with pytest.raises(ValueError, match="重复"):
        calculate_adjusted_k_line(k_lines, factors, "qfq")
