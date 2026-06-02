"""Top-level command line entry point."""

from __future__ import annotations

import click

from smhelper.live_assistant.interfaces.cli import create_live_assistant_cli


@click.group()
def main() -> None:
    """Self-media operations assistant."""


@click.command()
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Host interface for the web backend.",
)
@click.option(
    "--port",
    default=8000,
    show_default=True,
    type=int,
    help="Port for the web backend.",
)
@click.option(
    "--database-url",
    default=None,
    help="SQLAlchemy database URL. Defaults to SMHELPER_DATABASE_URL.",
)
def web(host: str, port: int, database_url: str | None) -> None:
    """Run the FastAPI and SQLAdmin management backend."""
    import uvicorn

    from smhelper.web.app import create_app

    app = create_app(database_url=database_url)
    uvicorn.run(app, host=host, port=port)


main.add_command(create_live_assistant_cli(), name="live-assistant")
main.add_command(web, name="web")
