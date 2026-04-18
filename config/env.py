from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        alias_generator=str.upper,
        populate_by_name=True,
    )

    discord_token: NonEmptyStr

    dev_mode: bool = False
    dev_guild_id: int | None = None
    dev_guild_only_commands: str = ""
    dev_dm_only_commands: str = ""
    sync_commands_on_start: bool = True

    toggl_token: NonEmptyStr | None = None
    toggl_saved_disabled: bool = True

    tick_disabled: bool = False
    tick_id: NonEmptyStr | None = None
    tick_secret: NonEmptyStr | None = None
    tick_uri: NonEmptyStr | None = None
    tick_email: NonEmptyStr | None = None
    tick_password: NonEmptyStr | None = None

    alias_disabled: bool = False

    mongo_uri: NonEmptyStr
    mongo_db: str = "productivity_bot"

    app_log_level: str = "INFO"
    lib_log_level: str = "WARNING"
    console_log_level: str = "INFO"
    app_log_file: str = "discord.log"
    dependency_log_file: str = "discord.deps.log"
    log_max_bytes: int = 32 * 1024 * 1024
    log_backup_count: int = 5

    openai_api_key: str | None = None

    alert_expiry_cleanup_minutes: int = 15

    pomodoro_audio_path: str | None = None
    pomodoro_break_audio_path: str | None = None
    pomodoro_audio_volume: float | None = None
    pomodoro_voice_assets: str | None = None

    @model_validator(mode="after")
    def validate_conditional_requirements(self) -> "Settings":
        if self.log_max_bytes < 1:
            raise ValueError("LOG_MAX_BYTES must be greater than 0.")
        if self.log_backup_count < 1:
            raise ValueError("LOG_BACKUP_COUNT must be greater than 0.")
        if self.alert_expiry_cleanup_minutes < 1:
            raise ValueError("ALERT_EXPIRY_CLEANUP_MINUTES must be greater than 0.")
        if self.pomodoro_audio_volume is not None and not (
            0.0 <= self.pomodoro_audio_volume <= 2.0
        ):
            raise ValueError("POMODORO_AUDIO_VOLUME must be between 0.0 and 2.0.")

        if self.tick_disabled:
            return self

        missing_fields = [
            field_name
            for field_name in (
                "TICK_ID",
                "TICK_SECRET",
                "TICK_URI",
                "TICK_EMAIL",
                "TICK_PASSWORD",
            )
            if not getattr(self, field_name.lower())
        ]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(
                "TickTick integration is enabled, but required environment "
                f"variables are missing: {missing}."
            )
        return self


try:
    settings = Settings()
except ValidationError as exc:
    raise RuntimeError(f"Invalid environment configuration:\n{exc}") from exc
