import hashlib
import hmac
import json

import pytest

from app.services.quote_provider import (
    QuoteProviderError,
    QuoteService,
    TradernetProvider,
    parse_tradernet_quote,
)


class Resp:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def test_symbol_mapping():
    assert TradernetProvider.symbol_for("hsbk") == "HSBK.KZ"
    assert TradernetProvider.symbol_for("PYPL_KZ.KZ") == "PYPL_KZ.KZ"
    assert TradernetProvider.symbol_for("AAPL.US") == "AAPL.US"


def test_request_is_signed_like_official_sdk():
    sent = {}

    def fake_post(url, headers, content, timeout):
        sent.update(url=url, headers=headers, content=content)
        return Resp({"result": {"q": [{"c": "HSBK.KZ", "ltp": 387.5, "x_curr": "KZT"}]}})

    p = TradernetProvider("pub", "secret", http_post=fake_post)
    assert p.fetch("HSBK") == (387.5, "KZT")
    assert sent["url"] == "https://freedom24.com/api/getStockQuotesJson"
    assert json.loads(sent["content"]) == {"tickers": "HSBK.KZ"}
    h = sent["headers"]
    expected = hmac.new(b"secret", (sent["content"] + h["X-NtApi-Timestamp"]).encode(), hashlib.sha256).hexdigest()
    assert h["X-NtApi-Sig"] == expected
    assert h["X-NtApi-PublicKey"] == "pub"


@pytest.mark.parametrize(
    "body",
    [
        {"result": {"q": [{"c": "CCBN.KZ", "ltp": "1990.5", "x_curr": "KZT"}]}},
        {"q": [{"c": "CCBN.KZ", "lp": 1990.5, "curr": "kzt"}]},
        [{"c": "ccbn.kz", "ltp": 0, "pp": 1990.5, "x_curr": "KZT"}],
    ],
)
def test_parse_variants(body):
    assert parse_tradernet_quote(body, "CCBN.KZ") == (1990.5, "KZT")


def test_parse_error_message():
    with pytest.raises(QuoteProviderError, match="bad key"):
        parse_tradernet_quote({"errMsg": "bad key"}, "HSBK.KZ")


def test_parse_missing_ticker():
    with pytest.raises(QuoteProviderError):
        parse_tradernet_quote({"result": {"q": []}}, "HSBK.KZ")


def test_disabled_without_keys():
    p = TradernetProvider("", "")
    assert not p.enabled
    with pytest.raises(QuoteProviderError):
        p.fetch("HSBK")


class Fake:
    def __init__(self, name, value=None):
        self.name = name
        self.value = value
        self.calls = 0
        self.enabled = True

    def fetch(self, ticker):
        self.calls += 1
        if self.value is None:
            raise QuoteProviderError("нет")
        return self.value


def test_kz_market_uses_tradernet_first(db, clock):
    tn = Fake("tradernet", (387.0, "KZT"))
    yahoo = Fake("yfinance", (1.0, "USD"))
    service = QuoteService(db, Fake("finnhub"), yahoo, now=clock, tradernet=tn)
    q = service.get_quote("HSBK", "KZ")
    assert (q.price, q.currency, q.source) == (387.0, "KZT", "tradernet")
    assert yahoo.calls == 0


def test_kz_market_falls_back_to_yahoo(db, clock):
    tn = Fake("tradernet")
    service = QuoteService(db, Fake("finnhub"), Fake("yfinance", (60.0, "USD")), now=clock, tradernet=tn)
    assert service.get_quote("PYPL", "KZ").source == "yfinance"


def test_us_market_does_not_use_tradernet(db, clock):
    tn = Fake("tradernet", (1.0, "USD"))
    service = QuoteService(db, Fake("finnhub", (195.0, "USD")), Fake("yfinance"), now=clock, tradernet=tn)
    assert service.get_quote("AAPL", "US").source == "finnhub"
    assert tn.calls == 0
