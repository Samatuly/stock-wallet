import time

import pytest

from app.services._timeout import run_with_timeout


def test_fast_call_returns_normally():
    assert run_with_timeout(lambda: 42, timeout_seconds=1.0) == 42


def test_slow_call_raises_timeout_error_instead_of_hanging():
    def slow():
        time.sleep(5)
        return "too late"

    with pytest.raises(TimeoutError):
        run_with_timeout(slow, timeout_seconds=0.2)


def test_timeout_does_not_block_the_caller():
    """Регрессия: реализация на 'with ThreadPoolExecutor' блокировала вызывающий
    код до завершения зависшего потока, сводя тайм-аут на нет. Здесь явно
    проверяем, что вызов возвращается быстро, а не через все 3 секунды сна."""

    def slow():
        time.sleep(3)
        return "too late"

    started = time.monotonic()
    with pytest.raises(TimeoutError):
        run_with_timeout(slow, timeout_seconds=0.2)
    elapsed = time.monotonic() - started
    assert elapsed < 1.0, f"run_with_timeout вернулся только через {elapsed:.2f} с — тайм-аут не работает"


def test_exception_inside_call_propagates():
    def boom():
        raise ValueError("что-то пошло не так")

    with pytest.raises(ValueError, match="что-то пошло не так"):
        run_with_timeout(boom, timeout_seconds=1.0)
