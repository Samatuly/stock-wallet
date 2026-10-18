# Stock Wallet

![tests](https://github.com/YOUR_USERNAME/stock-wallet/actions/workflows/tests.yml/badge.svg)

A personal stock portfolio tracker with live prices, multi-currency P&L and **probabilistic AI forecasts powered by Claude**.
Supports US, European and Kazakhstan markets.

> ⚠️ Educational / portfolio project. Forecasts are probabilistic estimates, **not investment advice**.

<!-- Replace with your screenshots (taken on demo data) -->
| Dashboard | Forecast | Mobile |
|---|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Forecast](docs/screenshots/forecast.png) | ![Mobile](docs/screenshots/mobile.png) |

## Features

- **Portfolio** — manual positions (multiple lots per ticker), fees, notes, CSV import.
- **Live prices & FX** — Finnhub / yfinance with caching, daily FX rates (Frankfurter), manual price override for illiquid tickers.
- **Dashboard** — allocation, ranked winners/losers, volatility table, benchmark comparison, price charts with indicators (pure SVG, no chart library).
- **Short-term forecast** — Monte Carlo simulation (5,000 paths) combined with a structured Claude analysis returned as validated JSON.
- **Long-term forecast** — 1/5/10-year bear/base/bull scenarios using a return-decomposition model:

  `1 + R = (1 + g)(1 + b)(1 + m) · (PE_T / PE_0)^(1/T)`

  (earnings growth, buybacks/dividends, margin change, valuation re-rating).
- **Forecast accuracy tracking** — matured forecasts are compared with actual prices.
- **What-if scenarios** — shock markets, single tickers or currencies and see the portfolio impact.
- **Decision journal & price alerts.**
- **Responsive UI** — burger menu, card layout on mobile.

## Engineering highlights

- **AI cost control** — every Claude call is metered by tokens; a hard monthly budget returns `HTTP 402` when exceeded. Forecasts are cached (24 h short-term, 30 days long-term).
- **Robust external data** — provider fallback chain, TTL caches in the DB, timeouts, NaN-safe history parsing.
- **Dependency injection** for all services → the test suite runs fully offline with fake providers.
- **~180 backend tests** (pytest), CI on every push (GitHub Actions).
- The API key lives only on the backend; the frontend never sees it.

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy 2, Pydantic v2, SQLite, httpx, yfinance |
| AI | Anthropic Claude API (direct HTTP, JSON-structured output) |
| Frontend | Next.js 15 (App Router), React 19, TypeScript, plain CSS, SVG charts |
| Tests / CI | pytest, GitHub Actions |

## Architecture

```
Next.js (frontend)  ──HTTP/JSON──►  FastAPI (backend)
                                      ├─ routers/   positions, quotes, dashboard, forecasts,
                                      │             journal, alerts, whatif
                                      ├─ services/  quotes, fx, history, fundamentals,
                                      │             monte_carlo, forecast, long_term, accuracy
                                      ├─ SQLite     positions + caches + saved forecasts
                                      └─► external: Finnhub / yfinance, Frankfurter FX, Claude API
```

## Getting started

**Backend** (Python 3.11+):

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env            # Windows: copy .env.example .env
python scripts/seed_demo.py     # optional: fake demo portfolio
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

**Frontend** (Node 20+):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. Claude forecasts are disabled until `ANTHROPIC_API_KEY` is set in `backend/.env`.

**Tests:**

```bash
cd backend
python -m pytest -q
```

## Data sources

Quotes come from free sources (yfinance, Finnhub free tier) intended for personal use. A commercial deployment would require a licensed market-data provider.

## Roadmap

- PWA / mobile install
- Authentication, PostgreSQL, hosted demo
- Native apps via Capacitor

## License

MIT — see [LICENSE](LICENSE).
