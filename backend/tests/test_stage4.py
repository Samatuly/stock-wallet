from datetime import date

import pytest

from app.services.csv_import import guess_market, parse_csv, parse_date, parse_number


# ---------- разбор чисел и дат ----------

@pytest.mark.parametrize("raw,expected", [
    ("12.5", 12.5), ("12,5", 12.5), ("1 234,56", 1234.56), ("1,234.56", 1234.56),
    ("1.234,56", 1234.56), ("$195.20", 195.20), ("1\xa0000", 1000.0),
])
def test_parse_number(raw, expected):
    assert parse_number(raw) == pytest.approx(expected)


def test_parse_number_rejects_garbage():
    for bad in ("", "abc", "-"):
        with pytest.raises(ValueError):
            parse_number(bad)


def test_parse_date_formats_and_ambiguity():
    assert parse_date("2026-03-25") == date(2026, 3, 25)
    assert parse_date("25.03.2026") == date(2026, 3, 25)
    assert parse_date("25/03/2026") == date(2026, 3, 25)   # 25 не может быть месяцем
    assert parse_date("03/25/2026") == date(2026, 3, 25)   # 25 не может быть месяцем
    with pytest.raises(ValueError, match="неоднозначна"):
        parse_date("03/04/2026")
    with pytest.raises(ValueError):
        parse_date("вчера")


def test_guess_market():
    assert guess_market("AAPL") == "US"
    assert guess_market("SAP.DE") == "EU"
    assert guess_market("KZTK.KZ") == "KZ"


# ---------- parse_csv ----------

def test_parse_csv_english_headers_comma():
    text = "ticker,quantity,price,date,fee\nAAPL,10,180.5,2026-01-15,1\nSAP.DE,5,140,2026-03-02,0\n"
    rows, errors = parse_csv(text)
    assert errors == []
    assert [(r.ticker, r.market, r.currency, r.quantity, r.buy_price, r.fee) for _, r in rows] == [
        ("AAPL", "US", "USD", 10, 180.5, 1), ("SAP.DE", "EU", "EUR", 5, 140, 0),
    ]
    assert [line for line, _ in rows] == [2, 3]


def test_parse_csv_russian_headers_semicolon_decimal_comma_and_bom():
    text = "﻿Тикер;Количество;Цена покупки;Дата;Валюта\nKZTK.KZ;100;1 250,50;15.02.2026;KZT\n"
    rows, errors = parse_csv(text)
    assert errors == []
    pos = rows[0][1]
    assert (pos.ticker, pos.market, pos.quantity, pos.buy_price, pos.buy_date) == (
        "KZTK.KZ", "KZ", 100, 1250.5, date(2026, 2, 15))


def test_parse_csv_reports_bad_rows_but_keeps_good_ones():
    text = (
        "ticker,quantity,price,date\n"
        "AAPL,10,180,2026-01-15\n"
        "MSFT,abc,300,2026-01-15\n"        # строка 3: плохое количество
        ",5,10,2026-01-15\n"               # строка 4: нет тикера
        "NVDA,2,100,03/04/2026\n"          # строка 5: неоднозначная дата
        "TSLA,-1,200,2026-01-15\n"         # строка 6: отрицательное количество
        "\n"
    )
    rows, errors = parse_csv(text)
    assert [r.ticker for _, r in rows] == ["AAPL"]
    assert sorted(line for line, _ in errors) == [3, 4, 5, 6]
    assert any("неоднозначна" in msg for _, msg in errors)


def test_parse_csv_missing_columns_is_one_clear_error():
    rows, errors = parse_csv("ticker,quantity\nAAPL,10\n")
    assert rows == [] and len(errors) == 1
    assert "цена покупки" in errors[0][1] and "дата" in errors[0][1]


def test_parse_csv_empty():
    assert parse_csv("   ")[1][0][1] == "файл пустой"


# ---------- импорт через API ----------

CSV = "ticker,quantity,price,date\nAAPL,10,180.5,2026-01-15\nSAP.DE,5,140,2026-03-02\n"


def test_import_dry_run_does_not_write(client):
    r = client.post("/positions/import", json={"csv_text": CSV, "dry_run": True})
    assert r.status_code == 200
    body = r.json()
    assert len(body["rows"]) == 2 and body["imported"] == 0
    assert client.get("/positions").json() == []


def test_import_writes_and_skips_duplicates(client):
    first = client.post("/positions/import", json={"csv_text": CSV, "dry_run": False}).json()
    assert first["imported"] == 2 and first["skipped_duplicates"] == 0
    assert len(client.get("/positions").json()) == 2

    again = client.post("/positions/import", json={"csv_text": CSV, "dry_run": False}).json()
    assert again["imported"] == 0 and again["skipped_duplicates"] == 2
    assert all(row["duplicate"] for row in again["rows"])
    assert len(client.get("/positions").json()) == 2

    # дубликат внутри одного файла тоже пропускается
    dup = "ticker,quantity,price,date\nMSFT,1,300,2026-01-01\nMSFT,1,300,2026-01-01\n"
    r = client.post("/positions/import", json={"csv_text": dup, "dry_run": False}).json()
    assert r["imported"] == 1 and r["skipped_duplicates"] == 1


def test_import_still_adds_valid_rows_when_some_fail(client):
    text = "ticker,quantity,price,date\nAAPL,10,180,2026-01-15\nBAD,x,1,2026-01-15\n"
    r = client.post("/positions/import", json={"csv_text": text, "dry_run": False}).json()
    assert r["imported"] == 1 and len(r["errors"]) == 1 and r["errors"][0]["line"] == 3


def test_import_route_does_not_clash_with_position_id(client):
    assert client.put("/positions/import", json={}).status_code in (404, 405, 422)
    assert client.post("/positions", json={
        "ticker": "AAPL", "market": "US", "quantity": 1, "buy_price": 1, "buy_date": "2026-01-01",
    }).status_code == 201


# ---------- журнал решений ----------

def test_journal_create_list_delete_with_price_change(client):
    r = client.post("/journal", json={
        "ticker": " aapl ", "action": "buy", "reason": "Сильный отчёт", "expectation": "рост за квартал",
    })
    assert r.status_code == 201
    entry = r.json()
    assert entry["ticker"] == "AAPL" and entry["price_at_entry"] == 195.2
    assert entry["current_price"] == 195.2 and entry["change_percent"] == 0.0

    listed = client.get("/journal").json()
    assert len(listed) == 1 and listed[0]["reason"] == "Сильный отчёт"
    assert client.get("/journal", params={"ticker": "msft"}).json() == []

    assert client.delete(f"/journal/{entry['id']}").status_code == 204
    assert client.delete(f"/journal/{entry['id']}").status_code == 404


def test_journal_saves_even_when_no_price(client):
    r = client.post("/journal", json={"ticker": "NOPRICE", "action": "watch", "reason": "слежу"})
    assert r.status_code == 201
    body = r.json()
    assert body["price_at_entry"] is None and body["change_percent"] is None


def test_journal_rejects_bad_action(client):
    assert client.post("/journal", json={"ticker": "AAPL", "action": "yolo"}).status_code == 422


# ---------- алерты ----------

def test_alert_fires_once_and_deactivates(client):
    above = client.post("/alerts", json={"ticker": "aapl", "direction": "above", "target_price": 190}).json()
    below = client.post("/alerts", json={"ticker": "AAPL", "direction": "below", "target_price": 150}).json()
    assert above["ticker"] == "AAPL" and above["active"] is True

    fired = client.post("/alerts/check").json()
    assert [a["id"] for a in fired] == [above["id"]]      # цена 195.2 выше 190, но не ниже 150
    assert fired[0]["triggered_price"] == 195.2 and fired[0]["active"] is False

    assert client.post("/alerts/check").json() == []      # повторно не срабатывает

    listed = {a["id"]: a for a in client.get("/alerts").json()}
    assert listed[above["id"]]["active"] is False and listed[below["id"]]["active"] is True
    assert listed[below["id"]]["current_price"] == 195.2


def test_alert_boundary_is_inclusive(client):
    client.post("/alerts", json={"ticker": "AAPL", "direction": "above", "target_price": 195.2})
    assert len(client.post("/alerts/check").json()) == 1


def test_alert_with_unavailable_price_stays_active(client):
    a = client.post("/alerts", json={"ticker": "GHOST", "direction": "above", "target_price": 1}).json()
    assert client.post("/alerts/check").json() == []
    assert client.get("/alerts").json()[0]["active"] is True and a["active"] is True


def test_alert_validation_and_delete(client):
    assert client.post("/alerts", json={"ticker": "AAPL", "direction": "up", "target_price": 1}).status_code == 422
    assert client.post("/alerts", json={"ticker": "AAPL", "direction": "above", "target_price": 0}).status_code == 422
    a = client.post("/alerts", json={"ticker": "AAPL", "direction": "above", "target_price": 500}).json()
    assert client.delete(f"/alerts/{a['id']}").status_code == 204
    assert client.delete(f"/alerts/{a['id']}").status_code == 404
