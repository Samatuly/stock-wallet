from sqlalchemy import create_engine, inspect, text

from app.db import ensure_columns


def test_ensure_columns_adds_actual_price_to_old_table_and_is_idempotent():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE forecasts (id INTEGER PRIMARY KEY, ticker VARCHAR(32))"))
        conn.execute(text("INSERT INTO forecasts (ticker) VALUES ('AAPL')"))
    ensure_columns(engine)
    ensure_columns(engine)  # повторный вызов не должен падать
    assert "actual_price" in {c["name"] for c in inspect(engine).get_columns("forecasts")}
    with engine.begin() as conn:
        assert conn.execute(text("SELECT ticker, actual_price FROM forecasts")).one() == ("AAPL", None)


def test_ensure_columns_without_table_does_nothing():
    ensure_columns(create_engine("sqlite://"))
