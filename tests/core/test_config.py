from __future__ import annotations

from pathlib import Path

import pytest

from smhelper.core.config import RuntimeSettings
from smhelper.core.exceptions import ConfigurationError


def test_runtime_settings_uses_env_state_path_and_default_platform(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state.json"
    profiles_dir = tmp_path / "profiles"

    settings = RuntimeSettings.from_env(
        {
            "SMHELPER_STATE_PATH": str(state_path),
            "SMHELPER_BROWSER_PROFILES_DIR": str(profiles_dir),
            "SMHELPER_DEFAULT_PLATFORM": "xhs",
        }
    )

    assert settings.state_path == state_path
    assert settings.browser_profiles_dir == profiles_dir
    assert settings.default_platform == "xhs"


def test_runtime_settings_uses_cwd_state_path_when_env_is_empty(
    tmp_path: Path,
) -> None:
    settings = RuntimeSettings.from_env({}, cwd=tmp_path)

    assert settings.state_path == tmp_path / ".smhelper" / "state.json"
    assert settings.browser_profiles_dir == tmp_path / ".smhelper" / "browser-profiles"


def test_runtime_settings_rejects_blank_platform(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="default platform"):
        RuntimeSettings.from_env(
            {"SMHELPER_DEFAULT_PLATFORM": " "},
            cwd=tmp_path,
        )
