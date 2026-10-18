from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import show_real_error


def test_global_handler_returns_structured_json_instead_of_generic_500():
    """Проверяет сам глобальный обработчик в изоляции: вместо голого
    "Internal Server Error" браузер должен получить тип и текст ошибки."""
    app = FastAPI()
    app.add_exception_handler(Exception, show_real_error)

    @app.get("/boom")
    def boom():
        raise ValueError("что-то пошло не так")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")

    assert resp.status_code == 500
    body = resp.json()
    assert body["error"] == "ValueError"
    assert body["detail"] == "что-то пошло не так"
    assert body["path"] == "/boom"
