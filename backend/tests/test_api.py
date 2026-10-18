POSITION = {
    "ticker": " aapl ",
    "market": "US",
    "quantity": 10,
    "buy_price": 180.50,
    "buy_date": "2026-01-15",
    "fee": 0,
    "currency": "usd",
    "note": "первая покупка",
}


def test_create_list_update_delete(client):
    created = client.post("/positions", json=POSITION)
    assert created.status_code == 201
    body = created.json()
    assert body["ticker"] == "AAPL" and body["currency"] == "USD"  # приведено к верхнему регистру

    assert len(client.get("/positions").json()) == 1

    updated = client.put(f"/positions/{body['id']}", json={**POSITION, "quantity": 12})
    assert updated.status_code == 200 and updated.json()["quantity"] == 12

    assert client.delete(f"/positions/{body['id']}").status_code == 204
    assert client.get("/positions").json() == []
    assert client.delete(f"/positions/{body['id']}").status_code == 404


def test_validation_rejects_bad_input(client):
    assert client.post("/positions", json={**POSITION, "quantity": 0}).status_code == 422
    assert client.post("/positions", json={**POSITION, "buy_price": -1}).status_code == 422
    assert client.post("/positions", json={**POSITION, "market": "XX"}).status_code == 422
    assert client.post("/positions", json={**POSITION, "ticker": "  "}).status_code == 422


def test_portfolio_endpoint_returns_pnl(client):
    client.post("/positions", json=POSITION)
    data = client.get("/portfolio").json()
    row = data["positions"][0]
    assert row["current_price"] == 195.2
    assert row["pnl_amount"] == 147.0 and row["pnl_percent"] == 8.14
    assert data["totals"][0]["currency"] == "USD"
    assert data["combined"]["currency"] == "USD"
    assert data["combined"]["value"] == 1952.0  # одна валюта: комбинированный итог совпадает с ним


def test_portfolio_combines_multiple_currencies(client):
    client.post("/positions", json=POSITION)  # AAPL, USD
    client.post("/positions", json={
        "ticker": "SAP.DE", "market": "EU", "quantity": 5, "buy_price": 140,
        "buy_date": "2026-03-02", "fee": 0, "currency": "EUR", "note": "",
    })
    client.put("/manual-prices", json={"ticker": "SAP.DE", "price": 150, "currency": "EUR"})

    usd = client.get("/portfolio?display_currency=USD").json()["combined"]
    eur = client.get("/portfolio?display_currency=EUR").json()["combined"]

    # 1952 USD + (5*150 EUR / 0.92) USD = 1952 + 815.22 = 2767.22
    assert usd["currency"] == "USD" and usd["value"] == round(1952 + 750 / 0.92, 2)
    # то же самое в евро: 1952 USD * 0.92 + 750 EUR
    assert eur["currency"] == "EUR" and eur["value"] == round(1952 * 0.92 + 750, 2)
    assert usd["missing_currencies"] == [] and not usd["is_stale"]


def test_unknown_ticker_can_get_manual_price(client):
    client.post("/positions", json={**POSITION, "ticker": "KZTK", "market": "KZ", "currency": "KZT",
                                    "buy_price": 40000})
    before = client.get("/portfolio").json()["positions"][0]
    assert before["current_price"] is None and before["warning"]

    resp = client.put("/manual-prices", json={"ticker": "kztk", "price": 42000, "currency": "kzt"})
    assert resp.status_code == 200

    after = client.get("/portfolio").json()["positions"][0]
    assert after["price_is_manual"] is True
    assert after["pnl_amount"] == 20000.0  # (42000 - 40000) * 10


def test_quote_endpoint(client):
    assert client.get("/quotes/AAPL").json()["price"] == 195.2
    assert client.get("/quotes/NOPE").status_code == 404


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_root_is_not_404(client):
    # Раньше GET / отдавал 404, что выглядело как ошибка при случайном открытии адреса
    assert client.get("/").status_code == 200


def test_history_endpoint_returns_points(client):
    rows = client.get("/quotes/AAPL/history").json()
    assert len(rows) == 3
    assert rows[0]["close"] < rows[-1]["close"]
    assert set(rows[0].keys()) == {"date", "open", "high", "low", "close", "volume"}


def test_dashboard_includes_benchmark_field_without_crashing(client):
    client.post("/positions", json=POSITION)
    data = client.get("/dashboard").json()
    assert "benchmark" in data  # None или заполненный объект — главное, что ключ есть и без ошибок


def test_dashboard_endpoint(client):
    client.post("/positions", json=POSITION)  # AAPL, цена 195.2 из FakeProvider
    data = client.get("/dashboard").json()
    assert data["display_currency"] == "USD"
    assert data["total_value"] == 1952.0
    assert data["allocation_by_ticker"][0]["label"] == "AAPL"
    assert data["allocation_by_ticker"][0]["percent"] == 100.0
    assert len(data["volatility"]) == 1
    # у фейкового провайдера истории 3 точки -> недостаточно для волатильности
    assert data["volatility"][0]["volatility_annualized"] is None


def test_indicators_endpoint(client):
    rows = client.get("/quotes/AAPL/indicators").json()
    assert set(rows.keys()) == {
        "dates", "close", "sma_20", "sma_50", "rsi_14", "macd", "macd_signal", "macd_histogram",
    }
    assert len(rows["close"]) == 3  # у фейкового провайдера в тестах 3 точки истории
    # данных мало -> все индикаторы ещё не определены
    assert all(v is None for v in rows["sma_20"])
    assert all(v is None for v in rows["rsi_14"])


def test_forecast_insufficient_history_returns_clear_error(client):
    client.post("/positions", json=POSITION)  # AAPL — тестовый клиент даёт всего 3 точки истории
    resp = client.post("/forecasts/AAPL", json={"horizon_days": 30})
    assert resp.status_code == 502
    assert "истори" in resp.json()["detail"].lower()


def test_forecast_budget_status_endpoint(client):
    resp = client.get("/forecasts/_budget/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["spent_usd"] == 0.0
    assert body["limit_usd"] == 10.0
    assert body["is_over_limit"] is False


def test_forecast_end_to_end_with_enough_history(client):
    """Подменяем сервис прогноза прямо внутри теста богатой историей (у общей
    тестовой заглушки истории всего 3 точки — этого мало для прогноза)."""
    import json as _json
    from datetime import date, timedelta

    from app.deps import get_forecast_service
    from app.main import app
    from app.services.forecast import ForecastService
    from app.services.fundamentals import FundamentalsService
    from app.services.history import Candle, HistoryService

    class RichHistoryProvider:
        def fetch(self_, ticker, days):
            today = date.today()
            return [
                Candle(date=today - timedelta(days=i), open=100, high=101, low=99,
                       close=100 + (i % 7), volume=1000)
                for i in range(60, 0, -1)
            ]

    class OkFundamentalsProvider:
        def fetch(self_, ticker):
            return {"trailingPE": 22.0}

    good = {
        "summary": "Сквозной тест.",
        "scenarios": [
            {"name": "optimistic", "probability": 0.3, "price_low": 110, "price_high": 120, "drivers": ["a"]},
            {"name": "base", "probability": 0.4, "price_low": 100, "price_high": 110, "drivers": ["b"]},
            {"name": "pessimistic", "probability": 0.3, "price_low": 90, "price_high": 100, "drivers": ["c"]},
        ],
        "prob_above_buy_price": 0.55,
        "key_risks": ["риск"],
        "confidence": "high",
        "data_gaps": [],
    }

    class FakeClaude:
        def complete_json(self_, package, extra_instruction=None, previous_response_text=None, max_tokens_override=None, system_prompt=None):
            class R:
                text = _json.dumps(good)
                input_tokens = 300
                output_tokens = 150

            return R()

    client.post("/positions", json=POSITION)  # AAPL — есть в заглушке котировок

    # Переиспользуем ту же сессию БД, что и у остальных подмен в этом тесте,
    # забирая её из текущего переопределения get_db, чтобы прогноз сохранился
    # в ту же базу, которую видит клиент.
    from app.db import get_db as _get_db
    db_session = app.dependency_overrides[_get_db]()

    app.dependency_overrides[get_forecast_service] = lambda: ForecastService(
        db_session,
        FakeClaude(),
        HistoryService(db_session, RichHistoryProvider()),
        FundamentalsService(db_session, OkFundamentalsProvider()),
    )

    resp = client.post("/forecasts/AAPL", json={"horizon_days": 30, "buy_price": 95})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["result"]["confidence"] == "high"
    assert body["monte_carlo"]["paths"] > 0
    assert body["from_cache"] is False
    assert body["cost_usd"] > 0

    # Повторный запрос без refresh должен взять из кэша
    resp2 = client.post("/forecasts/AAPL", json={"horizon_days": 30})
    assert resp2.json()["from_cache"] is True

    resp3 = client.get("/forecasts/AAPL", params={"horizon_days": 30})
    assert resp3.status_code == 200 and resp3.json()["from_cache"] is True


def test_accuracy_route_is_not_swallowed_by_ticker_route(client):
    resp = client.get("/forecasts/accuracy")
    assert resp.status_code == 200
    assert resp.json()["total_evaluated"] == 0 and resp.json()["items"] == []


def test_long_term_endpoint_end_to_end(client):
    import json as _json

    from app.db import get_db as _get_db
    from app.deps import get_long_term_service
    from app.main import app
    from app.services.forecast import ForecastService
    from app.services.fundamentals import FundamentalsService
    from app.services.history import Candle, HistoryService
    from app.services.long_term import LongTermForecastService

    good = {
        "summary": "Сквозной долгосрочный тест.",
        "scenarios": [
            {"name": n, "probability": p, "revenue_growth_annual": g, "net_buyback_annual": 0.01,
             "margin_change_annual": 0.0, "valuation_change_annual": 0.0, "rationale": "r"}
            for n, p, g in [("optimistic", 0.25, 0.08), ("base", 0.5, 0.05), ("pessimistic", 0.25, 0.01)]
        ],
        "benchmark_comparison_note": "",
        "confidence": "low",
        "data_gaps": [],
    }

    class FakeClaude:
        max_tokens = 4096

        def complete_json(self_, package, extra_instruction=None, previous_response_text=None,
                          max_tokens_override=None, system_prompt=None):
            class R:
                text = _json.dumps(good)
                input_tokens = 300
                output_tokens = 150

            return R()

    class NoHistory:
        def fetch(self_, ticker, days):
            return [Candle(date=__import__("datetime").date.today(), open=1, high=1, low=1, close=1, volume=1)]

    class Fund:
        def fetch(self_, ticker):
            return {"trailingPE": 20.0}

    db_session = app.dependency_overrides[_get_db]()
    hist, fund = HistoryService(db_session, NoHistory()), FundamentalsService(db_session, Fund())
    fs = ForecastService(db_session, FakeClaude(), hist, fund)
    app.dependency_overrides[get_long_term_service] = lambda: LongTermForecastService(
        db_session, FakeClaude(), hist, fund, budget_service=fs
    )
    client.post("/positions", json=POSITION)

    assert client.get("/forecasts/AAPL/long-term").json() is None
    resp = client.post("/forecasts/AAPL/long-term", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["from_cache"] is False
    assert [p["years"] for p in body["scenarios"][1]["points"]] == [1, 5, 10]
    assert body["benchmark_name"] == "Крупные акции США"
    assert client.post("/forecasts/AAPL/long-term", json={}).json()["from_cache"] is True
    assert client.get("/forecasts/AAPL/long-term").json()["from_cache"] is True
    # расход виден в общем месячном бюджете
    assert client.get("/forecasts/_budget/status").json()["spent_usd"] > 0
