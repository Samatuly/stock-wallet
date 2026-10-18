"""Регрессия: Yahoo Finance отдаёт NaN вместо цены для сегодняшнего ещё не
закрытого торгового дня. Если такую строку не отфильтровать, запись в SQLite
падает с IntegrityError (драйвер sqlite3 трактует NaN в числовой колонке как
NULL, а колонки цены — NOT NULL). См. реальный traceback, из-за которого нашли
этот баг: price_history.open NOT NULL constraint failed."""
import math
from datetime import date

import pandas as pd
import pytest

from app.models import PriceHistory
from app.services.history import HistoryService, parse_history_dataframe


def make_yfinance_df(rows: list[dict]) -> pd.DataFrame:
    """rows: [{"date": date(...), "Open": ..., "High": ..., "Low": ..., "Close": ..., "Volume": ...}]"""
    df = pd.DataFrame(rows).set_index("date")
    df.index = pd.to_datetime(df.index)
    return df


def test_nan_row_for_todays_incomplete_session_is_dropped():
    df = make_yfinance_df(
        [
            {"date": date(2026, 9, 29), "Open": 183.2, "High": 186.3, "Low": 182.3, "Close": 185.3, "Volume": 1_372_775},
            # сегодняшний день ещё не закрылся — Yahoo прислал NaN вместо цены
            {"date": date(2026, 9, 30), "Open": math.nan, "High": math.nan, "Low": math.nan, "Close": math.nan, "Volume": 2_259_749},
        ]
    )
    candles = parse_history_dataframe(df)
    assert len(candles) == 1
    assert candles[0].date == date(2026, 9, 29)


def test_partial_nan_in_single_field_is_also_dropped():
    df = make_yfinance_df(
        [{"date": date(2026, 9, 30), "Open": 183.2, "High": math.nan, "Low": 182.3, "Close": 185.3, "Volume": 100}]
    )
    assert parse_history_dataframe(df) == []


def test_normal_rows_pass_through_unchanged():
    df = make_yfinance_df(
        [{"date": date(2026, 9, 29), "Open": 183.2, "High": 186.3, "Low": 182.3, "Close": 185.3, "Volume": 1_372_775}]
    )
    candles = parse_history_dataframe(df)
    assert len(candles) == 1
    assert candles[0].close == 185.3


class NanThenCleanProvider:
    """Подделка источника: первая попытка возвращает NaN-свечу (как настоящий
    yfinance для сегодняшнего дня), что раньше приводило к падению записи в базу."""

    def fetch(self, ticker, days):
        from app.services.history import Candle

        return [
            Candle(date=date(2026, 9, 29), open=100, high=102, low=99, close=101, volume=1000),
            Candle(date=date(2026, 9, 30), open=math.nan, high=math.nan, low=math.nan, close=math.nan, volume=500),
        ]


def test_history_service_does_not_crash_on_nan_candle(db, clock):
    """Раньше это бросало sqlite3.IntegrityError и роняло весь запрос к /dashboard."""
    svc = HistoryService(db, NanThenCleanProvider(), now=clock)
    rows = svc.get_history("SAP.DE", days=30)
    assert len(rows) == 1  # NaN-свеча не попала в базу
    assert rows[0].close == 101
    saved = db.get(PriceHistory, ("SAP.DE", date(2026, 9, 30)))
    assert saved is None  # и не осталась в базе под сегодняшней датой
