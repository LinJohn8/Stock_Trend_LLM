from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "stock_ai_assistant"
    app_env: str = "local"
    database_url: str = "sqlite:///data/stock_ai_assistant.db"
    timezone: str = "Asia/Shanghai"

    email_enabled: bool = True
    email_send_time: str = Field("08:50,12:50", validation_alias=AliasChoices("EMAIL_SEND_TIMES", "EMAIL_SEND_TIME"))
    email_timezone: str = Field("Asia/Shanghai", validation_alias=AliasChoices("EMAIL_TIMEZONE", "TIMEZONE"))
    email_host: str = Field("smtp.qq.com", validation_alias=AliasChoices("EMAIL_HOST", "SMTP_SERVER"))
    email_port: int = Field(465, validation_alias=AliasChoices("EMAIL_PORT", "SMTP_PORT"))
    email_use_ssl: bool = True
    email_username: str = Field("", validation_alias=AliasChoices("EMAIL_USERNAME", "SENDER_EMAIL"))
    email_password: str = Field("", validation_alias=AliasChoices("EMAIL_PASSWORD", "SENDER_PASS"))
    email_from: str = Field("", validation_alias=AliasChoices("EMAIL_FROM", "SENDER_EMAIL"))
    email_to: str = Field("", validation_alias=AliasChoices("EMAIL_TO", "RECEIVER_EMAIL"))

    ai_enabled: bool = False
    ai_provider: Literal["openai", "deepseek", "glm", "mock"] = "deepseek"
    ai_api_key: str = ""
    ai_model: str = "deepseek-chat"
    ai_base_url: str = "https://api.deepseek.com/v1"

    stop_loss_threshold: float = -0.08
    take_profit_threshold: float = 0.20
    max_suggested_position: float = 0.30
    enable_news_analysis: bool = True
    enable_ai_summary: bool = True
    enable_signal_tracking: bool = True
    enable_dashboard_scheduler: bool = True

    port_range_start: int = 9690
    port_range_end: int = 9699
    api_preferred_port: int = 9690
    dashboard_preferred_port: int = 9696

    technical_weight: float = 0.30
    fundamental_weight: float = 0.25
    valuation_weight: float = 0.15
    capital_weight: float = 0.15
    news_weight: float = 0.10
    risk_weight: float = 0.05

    default_watchlist: str = "600519,300750,000001"

    @property
    def root_dir(self) -> Path:
        return ROOT_DIR

    @property
    def data_dir(self) -> Path:
        return ROOT_DIR / "data"

    @property
    def logs_dir(self) -> Path:
        return ROOT_DIR / "logs"

    @property
    def report_dir(self) -> Path:
        return ROOT_DIR / "reports" / "generated"

    @property
    def score_weights(self) -> dict[str, float]:
        return {
            "technical": self.technical_weight,
            "fundamental": self.fundamental_weight,
            "valuation": self.valuation_weight,
            "capital": self.capital_weight,
            "news": self.news_weight,
            "risk": self.risk_weight,
        }

    @property
    def email_send_time_list(self) -> list[str]:
        """Return configured report send times as HH:MM strings."""
        raw = self.email_send_time.replace("，", ",").replace(";", ",")
        times = [item.strip() for item in raw.split(",") if item.strip()]
        return times or ["08:50"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    return settings
