"""Runtime configuration primitives for CLI and infrastructure wiring."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from smhelper.core.exceptions import ConfigurationError


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Settings needed to wire the local runtime."""

    state_path: Path
    browser_profiles_dir: Path
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
            default_platform=platform,
        )
