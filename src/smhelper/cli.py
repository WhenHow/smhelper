"""Top-level command line entry point."""

from __future__ import annotations

import click

from smhelper.live_assistant.interfaces.cli import create_live_assistant_cli


@click.group()
def main() -> None:
    """Self-media operations assistant."""


main.add_command(create_live_assistant_cli(), name="live-assistant")
