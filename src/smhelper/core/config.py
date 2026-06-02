"""Runtime configuration primitives for CLI and infrastructure wiring."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from smhelper.core.exceptions import ConfigurationError

DEFAULT_DATABASE_URL = "mysql+pymysql://root:@127.0.0.1:3306/smhelper"
DEFAULT_CELERY_BROKER_URL = "redis://:tbui-666@127.0.0.1:6379/0"
DEFAULT_CELERY_RESULT_BACKEND_URL = "redis://:tbui-666@127.0.0.1:6379/1"
DEFAULT_SEND_COOLDOWN_SECONDS = 300


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Settings needed to wire the local runtime."""

    state_path: Path
    browser_profiles_dir: Path
    database_url: str
    celery_broker_url: str
    celery_result_backend_url: str
    send_cooldown_seconds: int
    default_platform: str = "xhs"

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> RuntimeSettings:
        """Create settings from environment variables.

        The default state path lives under the working directory so local CLI
        experiments do not require a database during the first iteration.
        """
        source = os.environ if env is None else env
        platform = source.get("SMHELPER_DEFAULT_PLATFORM", "xhs").strip()
        if not platform:
            raise ConfigurationError("default platform must not be blank")
        database_url = _required_setting(
            source.get("SMHELPER_DATABASE_URL"),
            default=DEFAULT_DATABASE_URL,
            name="database url",
        )
        celery_broker_url = _required_setting(
            source.get("SMHELPER_CELERY_BROKER_URL"),
            default=DEFAULT_CELERY_BROKER_URL,
            name="celery broker url",
        )
        celery_result_backend_url = _required_setting(
            source.get("SMHELPER_CELERY_RESULT_BACKEND_URL"),
            default=DEFAULT_CELERY_RESULT_BACKEND_URL,
            name="celery result backend url",
        )
        send_cooldown_seconds = _non_negative_int_setting(
            source.get("SMHELPER_SEND_COOLDOWN_SECONDS"),
            default=DEFAULT_SEND_COOLDOWN_SECONDS,
            name="send cooldown seconds",
        )

        raw_state_path = source.get("SMHELPER_STATE_PATH")
        state_path = (
            Path(raw_state_path)
            if raw_state_path
            else (cwd or Path.cwd()) / ".smhelper" / "state.json"
        )

        raw_profiles_dir = source.get("SMHELPER_BROWSER_PROFILES_DIR")
        browser_profiles_dir = (
            Path(raw_profiles_dir)
            if raw_profiles_dir
            else (cwd or Path.cwd()) / ".smhelper" / "browser-profiles"
        )
        return cls(
            state_path=state_path,
            browser_profiles_dir=browser_profiles_dir,
            database_url=database_url,
            celery_broker_url=celery_broker_url,
            celery_result_backend_url=celery_result_backend_url,
            send_cooldown_seconds=send_cooldown_seconds,
            default_platform=platform,
        )


def _required_setting(value: str | None, *, default: str, name: str) -> str:
    """Return a non-blank setting value or its default."""
    resolved = default if value is None else value.strip()
    if not resolved:
        raise ConfigurationError(f"{name} must not be blank")
    return resolved


def _non_negative_int_setting(
    value: str | None,
    *,
    default: int,
    name: str,
) -> int:
    """Return a non-negative integer setting value or its default."""
    raw = str(default) if value is None else value.strip()
    try:
        resolved = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a non-negative integer") from exc
    if resolved < 0:
        raise ConfigurationError(f"{name} must be a non-negative integer")
    return resolved
