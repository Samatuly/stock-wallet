"""Fill the database with a fake demo portfolio (for screenshots and live demo).

Usage (from the backend folder):
    python scripts/seed_demo.py                 # into the DB from .env / default
    python scripts/seed_demo.py --force         # wipe positions/journal/alerts first

Tip: keep your real data separate:
    set DATABASE_URL=sqlite:///./demo.db   (Windows)
    export DATABASE_URL=sqlite:///./demo.db (macOS/Linux)
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine, ensure_columns  # noqa: E402

TODAY = date.today()


def d(days_ago: int) -> date:
    return TODAY - timedelta(days=days_ago)


POSITIONS = [
    # ticker, market, qty, buy_price, days_ago, fee, currency, note
    ("AAPL", "US", 12, 172.40, 420, 1.0, "USD", "Core holding"),
    ("MSFT", "US", 6, 331.10, 380, 1.0, "USD", "Cloud + AI"),
    ("NVDA", "US", 10, 88.50, 300, 1.0, "USD", "Bought after split"),
    ("AAPL", "US", 5, 189.90, 120, 1.0, "USD", "Added on dip"),
    ("KO", "US", 20, 59.30, 600, 1.0, "USD", "Dividend"),
    ("SAP.DE", "EU", 8, 172.00, 250, 2.5, "EUR", "European software"),
    ("ASML.AS", "EU", 2, 690.00, 200, 2.5, "EUR", "Semis equipment"),
    ("DEMO.KZ", "KZ", 40, 3500.0, 150, 0.0, "KZT", "Demo KZ stock (manual price)"),
]

MANUAL_PRICES = [("DEMO.KZ", 3920.0, "KZT")]

JOURNAL = [
    ("NVDA", "US", "buy", "Data-center demand; accept high volatility.", "+30% within 12 months", 88.5, "USD", 300),
    ("KO", "US", "hold", "Stable dividend, defensive part of portfolio.", "Steady income", 61.0, "USD", 90),
    ("ASML.AS", "EU", "watch", "Would add below 600 EUR.", "Entry point", 640.0, "EUR", 30),
]

ALERTS = [
    ("NVDA", "US", "below", 100.0, "Consider adding"),
    ("AAPL", "US", "above", 260.0, "Take partial profit?"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="delete existing positions, journal and alerts")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    ensure_columns(engine)

    with SessionLocal() as db:
        if db.query(models.Position).count() and not args.force:
            sys.exit("Database already has positions. Use --force or point DATABASE_URL to a demo DB.")
        if args.force:
            for m in (models.Position, models.JournalEntry, models.PriceAlert, models.ManualPrice):
                db.query(m).delete()

        for t, mk, q, p, ago, fee, cur, note in POSITIONS:
            db.add(models.Position(ticker=t, market=mk, quantity=q, buy_price=p, buy_date=d(ago),
                                   fee=fee, currency=cur, note=note))
        for t, price, cur in MANUAL_PRICES:
            db.add(models.ManualPrice(ticker=t, price=price, currency=cur))
        for t, mk, action, reason, exp, price, cur, ago in JOURNAL:
            e = models.JournalEntry(ticker=t, market=mk, action=action, reason=reason, expectation=exp,
                                    price_at_entry=price, currency=cur)
            db.add(e)
            db.flush()
            e.created_at = e.created_at - timedelta(days=ago)
        for t, mk, direction, target, note in ALERTS:
            db.add(models.PriceAlert(ticker=t, market=mk, direction=direction, target_price=target, note=note))
        db.commit()

    print(f"Demo data added: {len(POSITIONS)} positions, {len(JOURNAL)} journal entries, {len(ALERTS)} alerts.")


if __name__ == "__main__":
    main()
