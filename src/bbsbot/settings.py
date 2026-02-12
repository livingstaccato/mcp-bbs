# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Application settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from bbsbot.llm.config import LLMConfig
from bbsbot.paths import default_knowledge_root


class Settings(BaseSettings):
    knowledge_root: Path = Field(default_factory=default_knowledge_root)
    log_level: str = "WARNING"
    llm: LLMConfig = Field(default_factory=LLMConfig)

    model_config = SettingsConfigDict(
        env_prefix="BBSBOT_",
        env_nested_delimiter="__",
        extra="ignore",
    )
