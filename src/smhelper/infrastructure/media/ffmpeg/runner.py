"""Command runner used by ffmpeg adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from subprocess import Popen, run
from typing import Protocol


class CommandRunner(Protocol):
    """Executes a command line."""

    def run(self, command: list[str]) -> None:
        """Run a command or raise on failure."""


class BackgroundProcessStarter(Protocol):
    """Starts a command in the background."""

    def start(self, command: list[str]) -> None:
        """Start a long-running command without waiting for completion."""


class SubprocessCommandRunner:
    """Command runner backed by subprocess.run."""

    def run(self, command: list[str]) -> None:
        """Run a command and fail if it exits non-zero."""
        run(command, check=True)


@dataclass(frozen=True, slots=True)
class SubprocessBackgroundProcessStarter:
    """Background process starter backed by subprocess.Popen."""

    popen: Callable[[list[str]], object] = Popen

    def start(self, command: list[str]) -> None:
        """Start a command and return immediately."""
        self.popen(command)
