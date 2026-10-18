from app.models import ManualPrice
from app.services.quote_provider import QuoteService
from tests.conftest import FakeProvider


def make(db, clock, finnhub=None, yahoo=None, ttl=300):
    finnhub = finnhub or FakeProvider("finnhub", {"AAPL": (195.2, "USD")})
    yahoo = yahoo or FakeProvider("yfinance", {"AAPL": (195.0, "USD"), "SAP.DE": (150.0, "EUR")})
    return QuoteService(db, finnhub, yahoo, ttl_seconds=ttl, now=clock), finnhub, yahoo


def test_us_uses_finnhub_first(db, clock):
    service, finnhub, yahoo = make(db, clock)
    quote = service.get_quote("AAPL", "US")
    assert quote.price == 195.2 and quote.source == "finnhub"
    assert yahoo.calls == []


def test_cache_is_used_within_ttl_and_refreshed_after(db, clock):
    service, finnhub, _ = make(db, clock, ttl=300)
    service.get_quote("AAPL", "US")
    clock.advance(299)
    service.get_quote("AAPL", "US")
    assert len(finnhub.calls) == 1  # второй раз взято из кэша
    clock.advance(2)
    service.get_quote("AAPL", "US")
    assert len(finnhub.calls) == 2  # кэш устарел


def test_force_refresh_ignores_cache(db, clock):
    service, finnhub, _ = make(db, clock)
    service.get_quote("AAPL", "US")
    service.get_quote("AAPL", "US", force=True)
    assert len(finnhub.calls) == 2


def test_falls_back_to_yahoo_when_finnhub_fails(db, clock):
    service, finnhub, yahoo = make(db, clock, finnhub=FakeProvider("finnhub", fail=True))
    quote = service.get_quote("AAPL", "US")
    assert quote.source == "yfinance" and quote.price == 195.0


def test_europe_and_kazakhstan_skip_finnhub(db, clock):
    service, finnhub, yahoo = make(db, clock)
    quote = service.get_quote("SAP.DE", "EU")
    assert quote.source == "yfinance" and quote.currency == "EUR"
    service.get_quote("KSPI.KZ", "KZ")
    assert finnhub.calls == []


def test_manual_price_is_last_resort_for_unknown_ticker(db, clock):
    service, _, _ = make(db, clock)
    assert service.get_quote("KZTK", "KZ") is None
    db.add(ManualPrice(ticker="KZTK", price=42000.0, currency="KZT", updated_at=clock()))
    db.commit()
    quote = service.get_quote("KZTK", "KZ")
    assert quote.is_manual and quote.source == "manual" and quote.price == 42000.0


def test_real_price_beats_manual_price(db, clock):
    service, _, _ = make(db, clock)
    db.add(ManualPrice(ticker="AAPL", price=1.0, currency="USD", updated_at=clock()))
    db.commit()
    assert service.get_quote("AAPL", "US").source == "finnhub"


def test_stale_cache_used_when_all_sources_fail(db, clock):
    finnhub = FakeProvider("finnhub", {"AAPL": (195.2, "USD")})
    service, _, _ = make(db, clock, finnhub=finnhub, yahoo=FakeProvider("yfinance", fail=True))
    service.get_quote("AAPL", "US")
    clock.advance(10_000)
    finnhub.fail = True
    quote = service.get_quote("AAPL", "US")
    assert quote.source == "cache-stale" and quote.price == 195.2


def test_get_quotes_requests_each_ticker_once(db, clock):
    service, finnhub, _ = make(db, clock)
    service.get_quotes([("AAPL", "US"), ("AAPL", "US"), ("aapl", "US")], force=True)
    assert len(finnhub.calls) == 1
