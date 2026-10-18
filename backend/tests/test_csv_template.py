"""Шаблон, который скачивается на странице импорта, должен разбираться без ошибок."""
from app.services.csv_import import parse_csv

TEMPLATE = (
    "﻿тикер;количество;цена покупки;дата;рынок;валюта;комиссия;комментарий\r\n"
    "AAPL;10;172,40;15.03.2025;US;USD;1;Первая покупка\r\n"
    "AAPL;5;189,90;20.06.2025;US;USD;1;Докупил на просадке\r\n"
    "SAP.DE;8;172,00;02.04.2025;EU;EUR;2,5;\r\n"
    "KSPI;3;95,10;10.01.2025;US;USD;0;Kaspi на Nasdaq\r\n"
)


def test_template_parses_without_errors():
    rows, errors = parse_csv(TEMPLATE)
    assert errors == []
    assert [p.ticker for _, p in rows] == ["AAPL", "AAPL", "SAP.DE", "KSPI"]
    assert rows[0][1].buy_price == 172.40
    assert rows[2][1].fee == 2.5
    assert rows[2][1].currency == "EUR"
