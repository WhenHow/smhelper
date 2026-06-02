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
    worker_storage_state_dir = tmp_path / "worker-storage-states"

    settings = RuntimeSettings.from_env(
        {
            "SMHELPER_STATE_PATH": str(state_path),
            "SMHELPER_BROWSER_PROFILES_DIR": str(profiles_dir),
            "SMHELPER_WORKER_STORAGE_STATE_DIR": str(worker_storage_state_dir),
            "SMHELPER_DEFAULT_PLATFORM": "xhs",
            "SMHELPER_DATABASE_URL": "mysql+pymysql://user:pass@db:3306/custom",
            "SMHELPER_CELERY_BROKER_URL": "redis://:secret@redis:6379/2",
            "SMHELPER_CELERY_RESULT_BACKEND_URL": "redis://:secret@redis:6379/3",
            "SMHELPER_CENTER_API_URL": "https://center.example",
            "SMHELPER_SEND_COOLDOWN_SECONDS": "300",
        }
    )

    assert settings.state_path == state_path
    assert settings.browser_profiles_dir == profiles_dir
    assert settings.worker_storage_state_dir == worker_storage_state_dir
    assert settings.default_platform == "xhs"
    assert settings.database_url == "mysql+pymysql://user:pass@db:3306/custom"
    assert settings.celery_broker_url == "redis://:secret@redis:6379/2"
    assert settings.celery_result_backend_url == "redis://:secret@redis:6379/3"
    assert settings.center_api_url == "https://center.example"
    assert settings.send_cooldown_seconds == 300


def test_runtime_settings_uses_cwd_state_path_when_env_is_empty(
    tmp_path: Path,
) -> None:
    settings = RuntimeSettings.from_env({}, cwd=tmp_path)

    assert settings.state_path == tmp_path / ".smhelper" / "state.json"
    assert settings.browser_profiles_dir == tmp_path / ".smhelper" / "browser-profiles"
    assert settings.worker_storage_state_dir == (
        tmp_path / ".smhelper" / "worker-storage-states"
    )
    assert settings.database_url == "mysql+pymysql://root:@127.0.0.1:3306/smhelper"
    assert settings.celery_broker_url == "redis://:tbui-666@127.0.0.1:6379/0"
    assert settings.celery_result_backend_url == "redis://:tbui-666@127.0.0.1:6379/1"
    assert settings.center_api_url == "http://127.0.0.1:8000"
    assert settings.send_cooldown_seconds == 300


def test_runtime_settings_rejects_blank_platform(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="default platform"):
        RuntimeSettings.from_env(
            {"SMHELPER_DEFAULT_PLATFORM": " "},
            cwd=tmp_path,
        )


def test_runtime_settings_rejects_invalid_send_cooldown(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="send cooldown"):
        RuntimeSettings.from_env(
            {"SMHELPER_SEND_COOLDOWN_SECONDS": "-1"},
            cwd=tmp_path,
        )
