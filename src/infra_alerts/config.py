from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    slack_webhook_url: str = Field(alias="SLACK_WEBHOOK_URL")
    twitterapi_io_key: str = Field(alias="TWITTERAPI_IO_KEY")

    gmail_address: str | None = Field(default=None, alias="GMAIL_ADDRESS")
    gmail_app_password: str | None = Field(default=None, alias="GMAIL_APP_PASSWORD")
    alert_email_recipients: str = Field(alias="ALERT_EMAIL_RECIPIENTS")
    allow_email_fallback: bool = Field(default=True, alias="ALLOW_EMAIL_FALLBACK")

    github_token: str | None = Field(default=None, alias="GITHUB_TOKEN")
    betterstack_enable_primary_gate: bool = Field(default=True, alias="BETTERSTACK_ENABLE_PRIMARY_GATE")
    betterstack_api_token: str | None = Field(default=None, alias="BETTERSTACK_API_TOKEN")
    betterstack_x_monitor_id: str | None = Field(default=None, alias="BETTERSTACK_X_MONITOR_ID")
    betterstack_twitterapi_monitor_id: str | None = Field(
        default=None,
        alias="BETTERSTACK_TWITTERAPI_MONITOR_ID",
    )

    x_status_url: str = Field(default="https://docs.x.com/status", alias="X_STATUS_URL")
    x_incidents_url: str = Field(default="https://docs.x.com/incidents", alias="X_INCIDENTS_URL")
    twitterapi_status_url: str = Field(default="https://twitterapi.io/status", alias="TWITTERAPI_STATUS_URL")
    x_changelog_url: str = Field(default="https://docs.x.com/changelog", alias="X_CHANGELOG_URL")
    twitterapi_changelog_url: str = Field(default="https://twitterapi.io/changelog", alias="TWITTERAPI_CHANGELOG_URL")
    twitterapi_sitemap_url: str = Field(default="https://twitterapi.io/sitemap.xml", alias="TWITTERAPI_SITEMAP_URL")
    twitterapi_sitemap_include_patterns: str = Field(
        default="/readme,/tweet-filter-rules,/changelog,/twitter/,/oapi/",
        alias="TWITTERAPI_SITEMAP_INCLUDE_PATTERNS",
    )
    twitterapi_sitemap_exclude_patterns: str = Field(
        default="/blog,/articles,/pricing,/qps-limits,/privacy,/contact,/payment,/affiliate-program",
        alias="TWITTERAPI_SITEMAP_EXCLUDE_PATTERNS",
    )
    github_docs_repo: str = Field(default="xdevplatform/docs", alias="GITHUB_DOCS_REPO")

    status_interval_minutes: int = Field(default=5, alias="STATUS_INTERVAL_MINUTES")
    tweets_interval_minutes: int = Field(default=30, alias="TWEETS_INTERVAL_MINUTES")
    docs_interval_minutes: int = Field(default=30, alias="DOCS_INTERVAL_MINUTES")
    digest_hour_local: int = Field(default=8, alias="DIGEST_HOUR_LOCAL")
    tz_name: str = Field(default="Europe/Lisbon", alias="TZ_NAME")

    status_backup_alert_delay_minutes: int = Field(default=10, alias="STATUS_BACKUP_ALERT_DELAY_MINUTES")
    unreachable_alert_after_failures: int = Field(default=3, alias="UNREACHABLE_ALERT_AFTER_FAILURES")
    watchdog_max_silence_minutes: int = Field(default=60, alias="WATCHDOG_MAX_SILENCE_MINUTES")

    max_links_per_alert: int = Field(default=20, alias="MAX_LINKS_PER_ALERT")
    retry_plan_minutes: str = Field(default="1,5,15,60", alias="RETRY_PLAN_MINUTES")
    retry_tail_minutes: int = Field(default=360, alias="RETRY_TAIL_MINUTES")
    retry_max_hours: int = Field(default=48, alias="RETRY_MAX_HOURS")

    state_path: str = Field(default="state/state.json", alias="STATE_PATH")
    pending_alerts_path: str = Field(default="state/pending_alerts.json", alias="PENDING_ALERTS_PATH")

    api_account_name: str = Field(default="API", alias="API_ACCOUNT_NAME")
    xdevelopers_account_name: str = Field(default="XDevelopers", alias="XDEVELOPERS_ACCOUNT_NAME")

    @model_validator(mode="after")
    def validate_email_fallback(self) -> Settings:
        if self.allow_email_fallback:
            if not self.gmail_address or not self.gmail_app_password:
                raise ValueError("GMAIL_ADDRESS and GMAIL_APP_PASSWORD are required when ALLOW_EMAIL_FALLBACK=true")
            if not self.email_recipients:
                raise ValueError("ALERT_EMAIL_RECIPIENTS must contain at least one email")
        if self.betterstack_enable_primary_gate:
            if not self.betterstack_api_token:
                raise ValueError("BETTERSTACK_API_TOKEN is required when BETTERSTACK_ENABLE_PRIMARY_GATE=true")
            if not self.betterstack_x_monitor_id:
                raise ValueError("BETTERSTACK_X_MONITOR_ID is required when BETTERSTACK_ENABLE_PRIMARY_GATE=true")
            if not self.betterstack_twitterapi_monitor_id:
                raise ValueError(
                    "BETTERSTACK_TWITTERAPI_MONITOR_ID is required when BETTERSTACK_ENABLE_PRIMARY_GATE=true"
                )
        return self

    @property
    def email_recipients(self) -> list[str]:
        return [item.strip() for item in self.alert_email_recipients.split(",") if item.strip()]

    @property
    def retry_minutes(self) -> list[int]:
        values = [chunk.strip() for chunk in self.retry_plan_minutes.split(",") if chunk.strip()]
        return [int(item) for item in values]

    @property
    def sitemap_include_patterns(self) -> list[str]:
        return [item.strip() for item in self.twitterapi_sitemap_include_patterns.split(",") if item.strip()]

    @property
    def sitemap_exclude_patterns(self) -> list[str]:
        return [item.strip() for item in self.twitterapi_sitemap_exclude_patterns.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
