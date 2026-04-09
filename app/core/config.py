from __future__ import annotations

from datetime import time
from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import TradingMode
from app.core.exceptions import ConfigurationError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Trade Automation MVP"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    json_logs: bool = True

    database_url: str = "sqlite:///./data/trade_automation.db"
    redis_url: str = "redis://localhost:6379/0"

    exchange_name: str = "kraken"
    exchange_api_key: str | None = None
    exchange_api_secret: str | None = None
    exchange_api_password: str | None = None
    default_quote_currency: str = "USDT"

    trading_mode: TradingMode = TradingMode.PAPER
    enable_live_trading: bool = False
    kill_switch: bool = False

    paper_starting_balance: float = 100000.0
    max_risk_per_trade: float = 0.01
    max_position_notional_pct: float = 0.20
    max_concurrent_positions: int = 3
    max_daily_loss_pct: float = 0.03
    max_drawdown_pct: float = 0.10
    max_spread_bps: float = 25.0
    max_slippage_bps: float = 20.0
    default_fee_bps: float = 10.0
    default_slippage_bps: float = 5.0
    stop_loss_cooldown_minutes: int = 30

    symbol_allowlist: str = "BTC/USDT,ETH/USDT,SOL/USDT"
    allowed_weekdays: str = "0,1,2,3,4,5,6"
    session_start_utc: str = "00:00"
    session_end_utc: str = "23:59"
    default_timeframes: str = "1m,5m,15m"

    auto_create_tables: bool = True
    scheduler_enabled: bool = False
    market_refresh_seconds: int = 60
    signal_evaluation_seconds: int = 60

    llm_features_enabled: bool = False
    openai_api_key: str | None = None
    claude_api_key: str | None = None

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    @property
    def symbol_allowlist_list(self) -> list[str]:
        return [item.strip() for item in self.symbol_allowlist.split(",") if item.strip()]

    @property
    def allowed_weekdays_list(self) -> list[int]:
        return [int(item.strip()) for item in self.allowed_weekdays.split(",") if item.strip()]

    @property
    def default_timeframes_list(self) -> list[str]:
        return [item.strip() for item in self.default_timeframes.split(",") if item.strip()]

    @property
    def session_start(self) -> time:
        return time.fromisoformat(self.session_start_utc)

    @property
    def session_end(self) -> time:
        return time.fromisoformat(self.session_end_utc)

    @property
    def live_trading_enabled(self) -> bool:
        return self.trading_mode == TradingMode.LIVE and self.enable_live_trading

    def require_live_trading_ready(self) -> None:
        if not self.live_trading_enabled:
            raise ConfigurationError(
                "Live trading requested without TRADING_MODE=live and ENABLE_LIVE_TRADING=true."
            )
        if not self.exchange_api_key or not self.exchange_api_secret:
            raise ConfigurationError(
                "Live trading requires EXCHANGE_API_KEY and EXCHANGE_API_SECRET."
            )

    def masked_config(self) -> dict[str, Any]:
        data = self.model_dump()
        for key in ("exchange_api_key", "exchange_api_secret", "exchange_api_password"):
            if data.get(key):
                data[key] = "***"
        return data


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
