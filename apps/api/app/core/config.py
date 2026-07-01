from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Agentic Hedge Fund"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://postgres:postgres@postgres:5432/agentic_hedge_fund"
    frontend_origin: str = "http://localhost:5173"

    dashscope_api_key: str = ""
    qwen_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    qwen_model_reasoning: str = "qwen3.7-plus"
    qwen_model_fast: str = "qwen3.7-flash"
    qwen_model_coder: str = "qwen3-coder-plus"
    qwen_json_mode: bool = True
    qwen_structured_output_strategy: str = "json_object"
    qwen_enable_thinking: bool = False
    qwen_temperature_analyst: float = 0.2
    qwen_temperature_debate: float = 0.35
    qwen_temperature_execution: float = 0.1
    qwen_max_context_chars_per_agent: int = 24_000
    qwen_max_tokens_per_agent: int = 1_200
    max_qwen_calls_per_cycle: int = 12
    max_qwen_tool_calls_per_agent: int = 6
    max_parallel_agent_calls: int = 5
    market_data_mode: str = "synthetic"
    real_market_tickers: str = "AAPL,NVDA,MSFT,TSLA,AMD,AMZN,META,GOOGL,JPM,XOM"
    yfinance_interval: str = "1m"
    yfinance_lookback_period: str = "5d"
    alpaca_api_key_id: str = ""
    alpaca_api_secret_key: str = ""
    alpaca_data_base_url: str = "https://data.alpaca.markets"
    alpaca_data_feed: str = "iex"
    simulation_trading_actions_enabled: bool = False
    simulation_recordings_dir: str = "recordings/simulations"

    initial_capital: float = Field(default=1_000_000.0)


def has_secret(value: str | None) -> bool:
    return bool(value and value.strip())


def resolve_llm_provider(settings: Settings) -> str:
    if has_secret(settings.dashscope_api_key):
        return "qwen"
    return "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
