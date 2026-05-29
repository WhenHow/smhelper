from __future__ import annotations

from click.testing import CliRunner

from smhelper import main


def test_main_exposes_live_assistant_command() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "live-assistant" in result.output
