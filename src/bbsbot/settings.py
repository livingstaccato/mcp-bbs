"""Application settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from bbsbot.paths import default_knowledge_root


class Settings(BaseSettings):
    knowledge_root: Path = Field(default_factory=default_knowledge_root)
    log_level: str = "WARNING"

    model_config = SettingsConfigDict(env_prefix="BBSBOT_", extra="ignore")
