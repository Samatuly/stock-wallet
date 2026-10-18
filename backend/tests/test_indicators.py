import pytest

from app.services.indicators import ema, macd, rsi, sma


def test_sma_matches_hand_calculation():
    # period=3: (1+2+3)/3=2, (2+3+4)/3=3, (3+4+5)/3=4
    result = sma([1, 2, 3, 4, 5], period=3)
    assert result == [None, None, 2, 3, 4]


def test_sma_of_constant_series_equals_the_constant():
    result = sma([5.0] * 10, period=4)
    assert all(v == 5.0 for v in result[3:])


def test_sma_none_when_not_enough_data():
    assert sma([1, 2], period=5) == [None, None]


def test_ema_of_constant_series_equals_the_constant():
    # EMA константы остаётся той же константой после "затравки"
    result = ema([10.0] * 15, period=5)
    assert result[:4] == [None, None, None, None]
    assert all(v == pytest.approx(10.0) for v in result[4:])


def test_ema_reacts_faster_than_sma_to_a_price_jump():
    closes = [10.0] * 10 + [20.0] * 10
    period = 5
    s = sma(closes, period)
    e = ema(closes, period)
    # В точке сразу после скачка EMA должна быть ближе к новой цене, чем SMA
    idx = 12
    assert e[idx] > s[idx]


def test_rsi_is_100_for_strictly_rising_prices():
    closes = list(range(1, 30))  # только рост, ни одного падения
    result = rsi(closes, period=14)
    assert result[14] == 100.0
    assert all(v == 100.0 for v in result[14:])


def test_rsi_is_0_for_strictly_falling_prices():
    closes = list(range(30, 1, -1))  # только падение
    result = rsi(closes, period=14)
    assert result[14] == 0.0


def test_rsi_none_until_enough_data():
    closes = [1, 2, 3, 4, 5]
    result = rsi(closes, period=14)
    assert all(v is None for v in result)


def test_macd_length_and_histogram_consistency():
    closes = [float(100 + i * 0.5) for i in range(60)]  # плавный рост
    macd_line, signal_line, histogram = macd(closes, fast=12, slow=26, signal=9)
    assert len(macd_line) == len(signal_line) == len(histogram) == len(closes)
    for m, s, h in zip(macd_line, signal_line, histogram):
        if m is not None and s is not None:
            assert h == pytest.approx(m - s)
        else:
            assert h is None


def test_macd_positive_for_sustained_uptrend():
    closes = [float(100 + i) for i in range(60)]  # устойчивый рост
    macd_line, _, _ = macd(closes)
    defined = [v for v in macd_line if v is not None]
    assert len(defined) > 0
    # Быстрая EMA растёт быстрее медленной при устойчивом росте -> MACD положительный
    assert all(v > 0 for v in defined)


def test_macd_none_when_too_short():
    macd_line, signal_line, histogram = macd([1.0, 2.0, 3.0])
    assert all(v is None for v in macd_line)
    assert all(v is None for v in signal_line)
    assert all(v is None for v in histogram)
