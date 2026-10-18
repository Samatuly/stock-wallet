import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import models  # noqa: F401  (регистрирует таблицы)
from app.config import get_settings
from app.db import Base, engine, ensure_columns
from app.routers import alerts, dashboard, forecasts, journal, portfolio, positions, quotes, whatif

log = logging.getLogger("stock_wallet.errors")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_columns(engine)
    yield


app = FastAPI(title="Stock Wallet", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(positions.router)
app.include_router(quotes.router)
app.include_router(portfolio.router)
app.include_router(dashboard.router)
app.include_router(forecasts.router)
app.include_router(journal.router)
app.include_router(alerts.router)
app.include_router(whatif.router)


@app.exception_handler(Exception)
async def show_real_error(request: Request, exc: Exception):
    """Личное локальное приложение, а не публичный сервис — поэтому вместо
    стандартного пустого "Internal Server Error" показываем в ответе тип и текст
    ошибки. Полный traceback всё равно пишется в лог сервера (в терминал), но
    теперь не обязательно туда лезть, чтобы понять, что сломалось."""
    log.error("Необработанная ошибка на %s %s:\n%s", request.method, request.url.path, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={
            "error": type(exc).__name__,
            "detail": str(exc),
            "path": request.url.path,
        },
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    """Не страница, а сам API. Если вы открыли этот адрес в браузере, значит бэкенд
    работает — сайт с портфелем находится на другом порту (обычно localhost:3000)."""
    return {"name": "Stock Wallet API", "docs": "/docs", "frontend": "смотрите на порту 3000"}
