import pandas as pd
import pytest

from market_data.calculated.returns import Returns


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
    result = Returns.calculate_returns(k_lines.iloc[::-1])
    assert result["trade_date"].tolist() == k_lines["trade_date"].tolist()
    assert pd.isna(result["daily_return"].iloc[0])
    assert result["daily_return"].iloc[1:].tolist() == pytest.approx([0.1, -0.1])
    assert result["cumulative_return"].tolist() == pytest.approx([0, 0.1, -0.01])
    assert (1 + result["daily_return"].iloc[1:]).prod() - 1 == pytest.approx(-0.01)
    pd.testing.assert_frame_equal(k_lines, original)


def test_multiple_stocks_have_separate_baselines(k_lines):
    other = k_lines.assign(code="sz.000333", close=["50", "50", "100"])
    result = Returns.calculate_returns(pd.concat([other, k_lines]).sample(frac=1, random_state=42))
    assert result.groupby("code")["daily_return"].apply(lambda values: values.isna().sum()).tolist() == [1, 1]
    assert result.loc[result["code"] == "sz.000333", "cumulative_return"].tolist() == [0, 0, 1]
    assert result.loc[result["code"] == "sh.600036", "cumulative_return"].iloc[-1] == pytest.approx(-0.01)


def test_single_trading_day(k_lines):
    result = Returns.calculate_returns(k_lines.iloc[[0]])
    assert pd.isna(result["daily_return"].iloc[0])
    assert result["cumulative_return"].iloc[0] == 0


def test_returns_are_invariant_to_adjustment_scale(k_lines):
    qfq = k_lines.assign(close=pd.to_numeric(k_lines["close"]) / 5, adjust_type="qfq")
    hfq_result = Returns.calculate_returns(k_lines)
    qfq_result = Returns.calculate_returns(qfq)
    for column in ("daily_return", "cumulative_return"):
        pd.testing.assert_series_equal(hfq_result[column], qfq_result[column])


@pytest.mark.parametrize("invalid", ["0", "-1", "nan", "inf", "bad", None])
def test_invalid_close_is_rejected(k_lines, invalid):
    k_lines.loc[1, "close"] = invalid
    with pytest.raises(ValueError, match="复权收盘价"):
        Returns.calculate_returns(k_lines)


def test_duplicate_date_is_rejected(k_lines):
    with pytest.raises(ValueError, match="重复"):
        Returns.calculate_returns(pd.concat([k_lines, k_lines.iloc[[0]]]))


def test_invalid_date_is_rejected(k_lines):
    k_lines.loc[1, "trade_date"] = "2026-02-30"
    with pytest.raises(ValueError, match="日期"):
        Returns.calculate_returns(k_lines)


def test_saved_returns_selection_and_recalculation(k_lines, tmp_path, monkeypatch):
    for code in ("sh.600036", "sz.000333"):
        path = tmp_path / "baostock/calculated/hfq_k_line" / f"{code}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        k_lines.assign(code=code).to_parquet(path, index=False)
    monkeypatch.setenv("A_STOCK_DATA_ROOT", str(tmp_path))
    calculator = Returns()
    summary = calculator.calculate_saved_returns(source="baostock", symbols=["sh.600036", "sh.600036"])
    assert len(summary["stocks"]) == 1
    stock = summary["stocks"][0]
    output = tmp_path / "baostock/calculated/returns/sh.600036.parquet"
    assert stock == {"code": "sh.600036", "rows": 3, "path": str(output)}
    saved = pd.read_parquet(output)
    assert saved["cumulative_return"].iloc[-1] == pytest.approx(-0.01)
    assert not (output.parent / "sz.000333.parquet").exists()
    original_path = tmp_path / "baostock/calculated/hfq_k_line/sh.600036.parquet"
    pd.testing.assert_frame_equal(pd.read_parquet(original_path), k_lines)
    changed = k_lines.copy()
    changed.loc[2, "close"] = "121"
    changed.to_parquet(original_path, index=False)
    calculator.calculate_saved_returns(source="baostock")
    assert pd.read_parquet(output)["cumulative_return"].iloc[-1] == pytest.approx(0.21)
    assert (output.parent / "sz.000333.parquet").exists()


def test_missing_saved_prices_are_reported(tmp_path):
    with pytest.raises(ValueError, match="找不到"):
        Returns(tmp_path).calculate_saved_returns(source="baostock")
