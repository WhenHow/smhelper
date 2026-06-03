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


@click.group()
def db() -> None:
    """Database maintenance commands."""


@click.command(name="init")
@click.option(
    "--database-url",
    default=None,
    help="SQLAlchemy database URL. Defaults to SMHELPER_DATABASE_URL.",
)
def init_database(database_url: str | None) -> None:
    """Create the configured database tables if they do not exist."""
    from smhelper.infrastructure.persistence.sqlalchemy.schema import (
        create_database_schema,
    )

    table_names = create_database_schema(database_url=database_url)
    click.echo(f"Initialized database schema with {len(table_names)} table(s).")


db.add_command(init_database)


@click.group()
def live() -> None:
    """Live assistant runtime commands."""


@click.command(name="doctor")
@click.option(
    "--database-url",
    default=None,
    help="SQLAlchemy database URL. Defaults to SMHELPER_DATABASE_URL.",
)
@click.pass_context
def live_doctor(ctx: click.Context, database_url: str | None) -> None:
    """Check whether the first-phase live runtime is ready to test."""
    from smhelper.infrastructure.persistence.sqlalchemy.live_doctor import (
        run_live_doctor,
    )

    report = run_live_doctor(database_url=database_url)
    click.echo(report.render())
    if report.has_failures:
        ctx.exit(1)


live.add_command(live_doctor)
main.add_command(create_live_assistant_cli(), name="live-assistant")
main.add_command(db, name="db")
main.add_command(live, name="live")
main.add_command(web, name="web")
