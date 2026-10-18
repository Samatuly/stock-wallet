"""Вызов Claude API для анализа пакета данных и прогноза.

Важно: Claude здесь НЕ ищет цены и не обращается к интернету сам — вся
математика (Monte Carlo) и все данные (индикаторы, фундаментал) уже посчитаны
нашим кодом и переданы в запросе. Роль Claude — прочитать это как аналитик и
дать качественную поправку с объяснением, а не придумывать числа с нуля.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable

import httpx

log = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Цены Sonnet 5 на момент написания (сентябрь 2026): $2 / $10 за млн токенов
# вход/выход. Если тариф изменится, поправить здесь.
PRICE_PER_MILLION_INPUT = 2.0
PRICE_PER_MILLION_OUTPUT = 10.0

SYSTEM_PROMPT = """Ты — финансовый аналитик, который помогает частному инвестору понять возможные сценарии по одной акции в его портфеле.

Жёсткие правила:
1. Ты не даёшь инвестиционных советов (не говоришь "покупай" или "продавай") и никогда не называешь одну точную будущую цену.
2. Используй только данные из присланного пакета. Не ищи и не выдумывай котировки, новости или цифры, которых там нет.
3. Если данных мало или они противоречивы, явно снижай уверенность (confidence) и перечисляй это в data_gaps.
4. Отвечай СТРОГО в формате JSON по схеме ниже, без текста до или после, без markdown-разметки (```), без пояснений.

Схема ответа:
{
  "summary": "2-3 предложения простым языком: что происходит и какие есть сценарии",
  "scenarios": [
    {"name": "optimistic", "probability": 0.0-1.0, "price_low": число, "price_high": число, "drivers": ["кратко, 1-3 пункта"]},
    {"name": "base", "probability": 0.0-1.0, "price_low": число, "price_high": число, "drivers": [...]},
    {"name": "pessimistic", "probability": 0.0-1.0, "price_low": число, "price_high": число, "drivers": [...]}
  ],
  "prob_above_buy_price": 0.0-1.0,
  "key_risks": ["кратко, 1-4 пункта"],
  "confidence": "low" | "medium" | "high",
  "data_gaps": ["чего не хватило в данных, если применимо, иначе пустой список"]
}

Сумма вероятностей трёх сценариев должна быть равна 1.0 (с точностью до округления).
Используй диапазон Monte Carlo (p10/p50/p90) из пакета как отправную точку для цен сценариев,
но можешь скорректировать веса вероятностей и диапазоны с учётом индикаторов, фундаментала и
даты ближайшего отчёта — и обязательно объясни в summary и drivers, если и почему скорректировал."""


class ClaudeError(Exception):
    """Не удалось получить или разобрать ответ Claude."""


class ClaudeTruncatedError(ClaudeError):
    """Ответ оборвался на середине — не хватило max_tokens.

    Как минимум у части моделей включено расширенное мышление, которое само
    расходует часть max_tokens ещё до видимого текста ответа. Если токенов
    на мышление ушло много, на сам JSON может не остаться места, и текст
    обрывается на середине строки — это и есть эта ошибка, а не поломанный
    JSON как таковой."""

    def __init__(self, message: str, input_tokens: int = 0, output_tokens: int = 0):
        super().__init__(message)
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


@dataclass
class ClaudeResponse:
    text: str
    input_tokens: int
    output_tokens: int

    @property
    def cost_usd(self) -> float:
        return round(
            self.input_tokens / 1_000_000 * PRICE_PER_MILLION_INPUT
            + self.output_tokens / 1_000_000 * PRICE_PER_MILLION_OUTPUT,
            6,
        )


class ClaudeClient:
    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-5",
        max_tokens: int = 1500,
        timeout_seconds: float = 30.0,
        http_post: Callable = httpx.post,
    ):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.http_post = http_post

    def complete_json(
        self,
        user_content: str,
        extra_instruction: str | None = None,
        previous_response_text: str | None = None,
        max_tokens_override: int | None = None,
        system_prompt: str | None = None,
    ) -> ClaudeResponse:
        """Отправляет пакет данных, возвращает ответ.

        Для повторного запроса-уточнения (например, "исправь сумму вероятностей")
        нужно передать и extra_instruction, и previous_response_text — то, что
        Claude ответил в прошлый раз. Так диалог остаётся с правильным
        чередованием ролей (user, assistant, user), а не двумя подряд
        сообщениями пользователя, которые Anthropic API тоже отклоняет.

        Раньше здесь было предзаполнение ответа сообщением {"role": "assistant",
        "content": "{"} — приём, чтобы Claude сразу начинал с JSON. Часть моделей
        (например, с обязательным расширенным мышлением) отвечает на это 400
        invalid_request_error: "This model does not support assistant message
        prefill. The conversation must end with a user message." Поэтому приём
        убран полностью — вместо него инструкция в системном промпте и
        устойчивый разбор ответа (parse_json_response снимает ```json-обёртку,
        если она всё же появится).
        """
        if not self.api_key:
            raise ClaudeError("ANTHROPIC_API_KEY не задан — добавьте его в backend/.env")

        messages = [{"role": "user", "content": user_content}]
        if extra_instruction:
            messages.append({"role": "assistant", "content": previous_response_text or ""})
            messages.append({"role": "user", "content": extra_instruction})

        body = {
            "model": self.model,
            "max_tokens": max_tokens_override or self.max_tokens,
            "system": system_prompt or SYSTEM_PROMPT,
            "messages": messages,
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        try:
            resp = self.http_post(API_URL, json=body, headers=headers, timeout=self.timeout_seconds)
        except httpx.HTTPError as exc:
            raise ClaudeError(f"Не удалось связаться с Claude API: {exc}") from exc

        if resp.status_code != 200:
            raise ClaudeError(f"Claude API вернул {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        try:
            text_blocks = [b["text"] for b in data["content"] if b.get("type") == "text"]
            text = "".join(text_blocks)
            usage = data["usage"]
            input_tokens = usage["input_tokens"]
            output_tokens = usage["output_tokens"]
            stop_reason = data.get("stop_reason")
        except (KeyError, TypeError) as exc:
            raise ClaudeError(f"Неожиданный формат ответа Claude: {exc}") from exc

        if stop_reason == "max_tokens":
            used = max_tokens_override or self.max_tokens
            raise ClaudeTruncatedError(
                f"Ответ Claude оборвался на середине — не хватило лимита max_tokens ({used}). "
                f"Использовано токенов: {output_tokens}.",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        return ClaudeResponse(text=text, input_tokens=input_tokens, output_tokens=output_tokens)


def _strip_markdown_fence(text: str) -> str:
    """На случай, если Claude всё же обернёт JSON в ```json ... ``` вопреки
    инструкции в системном промпте — снимаем обёртку перед разбором."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def parse_json_response(text: str) -> dict:
    cleaned = _strip_markdown_fence(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ClaudeError(f"Claude вернул невалидный JSON: {exc}. Текст: {cleaned[:300]}") from exc
