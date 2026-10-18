"""Жёсткое ограничение времени на блокирующий вызов (например, к yfinance).

yfinance не имеет официального API и не всегда соблюдает собственный параметр
timeout: иногда он всё равно зависает без ограничения по времени. Эта обёртка
даёт гарантию на уровне нашего кода: если вызов не уложился в timeout_seconds,
мы прерываем ожидание и считаем источник недоступным — вместо того чтобы
запрос к /portfolio или /dashboard завис на неопределённое время.

Сам поток с вызовом при этом может остаться "висеть" в фоне (Python не умеет
принудительно убивать поток) — это приемлемая цена за то, что пользователь
получает ответ за разумное время.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Callable, TypeVar

T = TypeVar("T")


def run_with_timeout(fn: Callable[[], T], timeout_seconds: float) -> T:
    # Намеренно без "with": ThreadPoolExecutor.__exit__ вызывает shutdown(wait=True)
    # и заблокировался бы до завершения зависшего потока — то есть свёл бы весь
    # смысл тайм-аута на нет. Вместо этого явно завершаем пул с wait=False на обоих
    # путях: поток может доработать в фоне, но вызывающий код ждать не будет.
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn)
    try:
        result = future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        pool.shutdown(wait=False)
        raise TimeoutError(f"превышено время ожидания ({timeout_seconds:.0f} с)") from exc
    else:
        pool.shutdown(wait=False)
        return result
