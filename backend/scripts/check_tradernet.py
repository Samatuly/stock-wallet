"""Проверка ключей Freedom/Tradernet: получает цены нескольких бумаг KASE.

Запуск из папки backend:
    python scripts/check_tradernet.py HSBK CCBN
    python scripts/check_tradernet.py HSBK --raw     # показать ответ сервера целиком

Ключи берутся из backend/.env и на экран НЕ выводятся.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.services.quote_provider import QuoteProviderError, TradernetProvider, parse_tradernet_quote  # noqa: E402

DOMAINS = ("freedom24.com", "tradernet.kz", "tradernet.global")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    raw = "--raw" in sys.argv
    tickers = args or ["HSBK", "CCBN"]
    s = get_settings()
    if not (s.tradernet_public_key and s.tradernet_private_key):
        sys.exit("В backend/.env нет TRADERNET_PUBLIC_KEY и/или TRADERNET_PRIVATE_KEY (нужны ОБА ключа).")

    domains = [s.tradernet_domain] + [d for d in DOMAINS if d != s.tradernet_domain]
    for domain in domains:
        p = TradernetProvider(s.tradernet_public_key, s.tradernet_private_key, domain=domain)
        print(f"\n== {domain} ==")
        ok = 0
        for t in tickers:
            symbol = p.symbol_for(t)
            try:
                data = p.request("getStockQuotesJson", {"tickers": symbol})
            except Exception as exc:
                print(f"  {symbol}: ошибка запроса: {exc}")
                continue
            if raw:
                print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
            try:
                price, cur = parse_tradernet_quote(data, symbol)
                print(f"  {symbol}: {price} {cur or ''}")
                ok += 1
            except QuoteProviderError as exc:
                print(f"  {symbol}: {exc}")
        if ok:
            if domain != s.tradernet_domain:
                print(f"\nРаботает домен {domain}: добавьте в backend/.env строку TRADERNET_DOMAIN={domain}")
            return
    print("\nНи один домен не вернул цены. Запустите с --raw и пришлите вывод (ключей в нём нет).")


if __name__ == "__main__":
    main()
