"""Технические индикаторы по дневным ценам закрытия.

Эти же функции на этапе 3 будут использоваться для сбора данных для прогноза
Claude — поэтому расчёт сделан на бэкенде, а не на фронтенде: один источник
истины для графика и для будущего анализа.

Все функции возвращают список той же длины, что и вход: там, где данных ещё
не накопилось, стоит None — это проще рисовать на графике (просто обрыв линии),
чем сдвигать индексы.
"""
from __future__ import annotations

from typing import Optional


def sma(closes: list[float], period: int) -> list[Optional[float]]:
    """Простая скользящая средняя."""
    result: list[Optional[float]] = [None] * len(closes)
    if period <= 0 or len(closes) < period:
        return result
    window_sum = sum(closes[:period])
    result[period - 1] = window_sum / period
    for i in range(period, len(closes)):
        window_sum += closes[i] - closes[i - period]
        result[i] = window_sum / period
    return result


def ema(closes: list[float], period: int) -> list[Optional[float]]:
    """Экспоненциальная скользящая средняя. Первое значение — простая средняя
    за period точек (стандартная "затравка"), дальше обычная формула EMA."""
    result: list[Optional[float]] = [None] * len(closes)
    if period <= 0 or len(closes) < period:
        return result
    k = 2 / (period + 1)
    prev = sum(closes[:period]) / period
    result[period - 1] = prev
    for i in range(period, len(closes)):
        prev = closes[i] * k + prev * (1 - k)
        result[i] = prev
    return result


def rsi(closes: list[float], period: int = 14) -> list[Optional[float]]:
    """RSI по сглаживанию Уайлдера — та же формула, что в большинстве платформ.
    Диапазон 0-100: выше 70 обычно считают перекупленностью, ниже 30 —
    перепроданностью, но это ориентир, а не жёсткое правило."""
    n = len(closes)
    result: list[Optional[float]] = [None] * n
    if n <= period:
        return result

    gains, losses = [], []
    for i in range(1, n):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def _value(ag: float, al: float) -> float:
        if al == 0:
            return 100.0 if ag > 0 else 0.0  # нет ни роста, ни падения -> нейтрально считаем "0 потерь"
        return 100 - (100 / (1 + ag / al))

    result[period] = _value(avg_gain, avg_loss)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        result[i + 1] = _value(avg_gain, avg_loss)
    return result


def macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[Optional[float]], list[Optional[float]], list[Optional[float]]]:
    """Возвращает (линия MACD, сигнальная линия, гистограмма), каждая — список
    той же длины, что closes."""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line: list[Optional[float]] = [
        (f - s) if f is not None and s is not None else None for f, s in zip(ema_fast, ema_slow)
    ]

    valid = [v for v in macd_line if v is not None]
    offset = len(macd_line) - len(valid)
    signal_from_valid = ema(valid, signal)
    signal_line: list[Optional[float]] = [None] * len(closes)
    for i, v in enumerate(signal_from_valid):
        signal_line[offset + i] = v

    histogram: list[Optional[float]] = [
        (m - s) if m is not None and s is not None else None for m, s in zip(macd_line, signal_line)
    ]
    return macd_line, signal_line, histogram
