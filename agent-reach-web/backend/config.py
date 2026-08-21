# ──────────────────────────────────────────────────────────────────────
# config.py — Centralised settings loaded from environment / .env file
# ──────────────────────────────────────────────────────────────────────
from __future__ import annotations

import os
import shutil
from pathlib import Path
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application-wide settings.

    Values are loaded in this priority order:
      1. Environment variables
      2. .env file in the backend directory
      3. Defaults defined here
    """

    # ── Application ──────────────────────────────────────────────────
    app_title: str = "Agent Reach Web"
    app_version: str = "1.0.0"

    # ── Security ─────────────────────────────────────────────────────
    api_secret_key: str = "change-me-to-a-random-string"

    # ── CORS ─────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ── Agent Reach ──────────────────────────────────────────────────
    agent_reach_bin: str = ""
    command_timeout: int = Field(default=120, ge=5, le=600)
    groq_api_key: str | None = None
    nvidia_api_key: str | None = None

    model_config = {
        "env_file": str(Path(__file__).resolve().parent / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    # ── Helpers ──────────────────────────────────────────────────────

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse the comma-separated CORS_ORIGINS string into a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def resolved_bin(self) -> str:
        """Return the resolved path to the agent-reach binary.

        Resolution order:
          1. Explicit ``AGENT_REACH_BIN`` env var
          2. ``~/.agent-reach-venv/Scripts/agent-reach.exe`` (Windows venv)
          3. ``~/.agent-reach-venv/bin/agent-reach`` (Linux/macOS venv)
          4. ``agent-reach`` on ``$PATH``
        """
        if self.agent_reach_bin:
            return self.agent_reach_bin

        home = Path.home()

        # Windows venv location
        win_path = home / ".agent-reach-venv" / "Scripts" / "agent-reach.exe"
        if win_path.is_file():
            return str(win_path)

        # Linux / macOS venv location
        unix_path = home / ".agent-reach-venv" / "bin" / "agent-reach"
        if unix_path.is_file():
            return str(unix_path)

        # Fall back to PATH
        found = shutil.which("agent-reach")
        if found:
            return found

        raise FileNotFoundError(
            "agent-reach binary not found. Set AGENT_REACH_BIN in your .env "
            "or install Agent Reach into ~/.agent-reach-venv."
        )


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — call this instead of constructing Settings directly."""
    return Settings()
