"""Command runner used by ffmpeg adapters."""

from __future__ import annotations

from subprocess import run
from typing import Protocol


class CommandRunner(Protocol):
    """Executes a command line."""

    def run(self, command: list[str]) -> None:
        """Run a command or raise on failure."""


class SubprocessCommandRunner:
    """Command runner backed by subprocess.run."""

    def run(self, command: list[str]) -> None:
        """Run a command and fail if it exits non-zero."""
        run(command, check=True)
