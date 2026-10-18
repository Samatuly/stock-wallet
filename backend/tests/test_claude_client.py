import json

import httpx
import pytest

from app.services.claude_client import ClaudeClient, ClaudeError, ClaudeTruncatedError, parse_json_response


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def anthropic_ok(text: str, input_tokens=500, output_tokens=200, stop_reason="end_turn"):
    def _post(url, json=None, headers=None, timeout=None):
        return FakeResponse(
            200,
            {
                "content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
                "stop_reason": stop_reason,
            },
        )
    return _post


def test_requires_api_key():
    client = ClaudeClient(api_key="")
    with pytest.raises(ClaudeError, match="ANTHROPIC_API_KEY"):
        client.complete_json("{}")


def test_first_request_does_not_end_with_assistant_message():
    """Регрессия: раньше здесь было предзаполнение ответа сообщением от имени
    ассистента, идущим последним в списке. Часть моделей отвечает на это 400
    "This model does not support assistant message prefill. The conversation
    must end with a user message." — проверяем, что такого сообщения больше нет."""
    captured = {}

    def _post(url, json=None, headers=None, timeout=None):
        captured["messages"] = json["messages"]
        return FakeResponse(200, {"content": [{"type": "text", "text": "{}"}], "usage": {"input_tokens": 1, "output_tokens": 1}})

    client = ClaudeClient(api_key="sk-test", http_post=_post)
    client.complete_json("packet")
    assert captured["messages"][-1]["role"] == "user"
    assert all(m["role"] != "assistant" for m in captured["messages"])


def test_response_text_returned_as_is_without_prefill_tricks():
    client = ClaudeClient(api_key="sk-test", http_post=anthropic_ok('{"summary": "ok"}'))
    response = client.complete_json("{}")
    assert response.text == '{"summary": "ok"}'


def test_parse_strips_markdown_fence_if_claude_adds_one_anyway():
    client = ClaudeClient(api_key="sk-test", http_post=anthropic_ok('```json\n{"summary": "ok"}\n```'))
    response = client.complete_json("{}")
    assert parse_json_response(response.text) == {"summary": "ok"}


def test_cost_calculation():
    client = ClaudeClient(api_key="sk-test", http_post=anthropic_ok("{}", input_tokens=1_000_000, output_tokens=1_000_000))
    response = client.complete_json("{}")
    assert response.cost_usd == pytest.approx(2.0 + 10.0)


def test_non_200_status_raises_claude_error():
    def _post(url, json=None, headers=None, timeout=None):
        return FakeResponse(500, text="internal error")
    client = ClaudeClient(api_key="sk-test", http_post=_post)
    with pytest.raises(ClaudeError, match="500"):
        client.complete_json("{}")


def test_network_error_raises_claude_error():
    def _post(url, json=None, headers=None, timeout=None):
        raise httpx.ConnectError("нет сети")
    client = ClaudeClient(api_key="sk-test", http_post=_post)
    with pytest.raises(ClaudeError, match="связаться"):
        client.complete_json("{}")


def test_unexpected_response_shape_raises_claude_error():
    def _post(url, json=None, headers=None, timeout=None):
        return FakeResponse(200, {"unexpected": "shape"})
    client = ClaudeClient(api_key="sk-test", http_post=_post)
    with pytest.raises(ClaudeError, match="формат"):
        client.complete_json("{}")


def test_extra_instruction_keeps_correct_role_alternation():
    """Диалог должен чередоваться user -> assistant -> user. Предыдущий (неверный)
    ответ Claude возвращается в разговор как есть, от его собственного имени,
    а не два сообщения пользователя подряд (это тоже отклоняется Anthropic API)."""
    captured = {}

    def _post(url, json=None, headers=None, timeout=None):
        captured["body"] = json
        return FakeResponse(
            200,
            {"content": [{"type": "text", "text": "fixed"}], "usage": {"input_tokens": 10, "output_tokens": 5}},
        )

    client = ClaudeClient(api_key="sk-test", http_post=_post)
    client.complete_json(
        "{}", extra_instruction="исправь вероятности", previous_response_text='{"bad": "response"}'
    )
    messages = captured["body"]["messages"]
    assert messages[-1] == {"role": "user", "content": "исправь вероятности"}
    assert messages[-2] == {"role": "assistant", "content": '{"bad": "response"}'}
    assert messages[-3] == {"role": "user", "content": "{}"}
    roles = [m["role"] for m in messages]
    assert roles == ["user", "assistant", "user"]


def test_truncated_response_raises_claude_truncated_error():
    """Регрессия: ответ оборвался на середине (не хватило max_tokens) — у части
    моделей расширенное мышление само расходует часть лимита. Раньше это
    проявлялось как невнятная ошибка разбора JSON ("Unterminated string...")."""
    client = ClaudeClient(
        api_key="sk-test",
        http_post=anthropic_ok('{"summary": "обрыв на полу', output_tokens=1500, stop_reason="max_tokens"),
    )
    with pytest.raises(ClaudeTruncatedError, match="оборвался на середине"):
        client.complete_json("{}")


def test_truncated_error_carries_token_usage_for_billing():
    client = ClaudeClient(
        api_key="sk-test",
        http_post=anthropic_ok("частичный текст", input_tokens=700, output_tokens=1500, stop_reason="max_tokens"),
    )
    with pytest.raises(ClaudeTruncatedError) as exc_info:
        client.complete_json("{}")
    assert exc_info.value.input_tokens == 700
    assert exc_info.value.output_tokens == 1500


def test_max_tokens_override_is_sent_to_api():
    captured = {}

    def _post(url, json=None, headers=None, timeout=None):
        captured["max_tokens"] = json["max_tokens"]
        return FakeResponse(200, {"content": [{"type": "text", "text": "{}"}],
                                   "usage": {"input_tokens": 1, "output_tokens": 1}, "stop_reason": "end_turn"})

    client = ClaudeClient(api_key="sk-test", max_tokens=1500, http_post=_post)
    client.complete_json("{}", max_tokens_override=3000)
    assert captured["max_tokens"] == 3000


def test_normal_completion_with_end_turn_does_not_raise():
    client = ClaudeClient(api_key="sk-test", http_post=anthropic_ok('{"ok": true}', stop_reason="end_turn"))
    response = client.complete_json("{}")
    assert response.text == '{"ok": true}'


def test_parse_json_response_valid():
    assert parse_json_response('{"a": 1}') == {"a": 1}


def test_parse_json_response_invalid_raises_claude_error():
    with pytest.raises(ClaudeError, match="невалидный JSON"):
        parse_json_response("это не json")
