from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения. Значения берутся из переменных окружения или файла .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    finnhub_api_key: str = ""
    # Freedom Broker / Tradernet: котировки KASE. Ключи создаются в личном кабинете Freedom.
    tradernet_public_key: str = ""
    tradernet_private_key: str = ""
    tradernet_domain: str = "freedom24.com"
    database_url: str = "sqlite:///./stockwallet.db"
    price_ttl_seconds: int = 300
    fx_ttl_seconds: int = 86400  # курсы валют обновляются не чаще раза в сутки
    history_ttl_seconds: int = 86400  # история цены обновляется не чаще раза в сутки
    fundamentals_ttl_seconds: int = 86400  # P/E и дивиденды тоже не чаще раза в сутки

    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5"
    # 1500 оказалось мало: у части моделей включено расширенное мышление,
    # которое само расходует часть max_tokens ещё до видимого текста ответа,
    # и JSON обрывался на середине. Подняли с запасом; реальная стоимость
    # зависит от того, сколько токенов Claude фактически использует, а не
    # от этого потолка — поднять его безопасно для бюджета.
    claude_max_tokens: int = 4096
    forecast_ttl_seconds: int = 86400  # прогноз на тикер+горизонт не чаще раза в сутки
    long_term_forecast_ttl_seconds: int = 30 * 86400  # долгосрочный прогноз живёт 30 дней
    forecast_monthly_budget_usd: float = 10.0
    monte_carlo_paths: int = 5000
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
