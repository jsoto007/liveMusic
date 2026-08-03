"""Operator commands: `flask media sweep`, `flask seed demo`."""

import click
from flask.cli import AppGroup

from .extensions import db


def register_cli(app) -> None:
    media = AppGroup("media", help="Media and storage maintenance.")
    seed = AppGroup("seed", help="Seed data for local development.")

    @media.command("sweep")
    def sweep():
        """Delete objects left behind by uploads that were never completed."""
        from .services.upload_sweeper import sweep_abandoned_uploads

        result = sweep_abandoned_uploads()
        click.echo(
            f"Swept {result['tickets']} expired tickets, "
            f"removed {result['objects_deleted']} objects."
        )

    @seed.command("demo")
    @click.option("--city", default="Providence", show_default=True)
    def demo(city: str):
        """Populate a local database with a readable week of listings."""
        if not app.config.get("IS_DEVELOPMENT") and not app.config.get("TESTING"):
            raise click.ClickException(
                "Refusing to seed demo data outside a development environment."
            )
        from .seed import seed_demo_data

        summary = seed_demo_data(db.session, city=city)
        click.echo(
            f"Seeded {summary['venues']} venues, {summary['artists']} bands, "
            f"{summary['events']} listings in {city}."
        )

    notify = AppGroup("notify", help="Scheduled notifications.")

    @notify.command("reminders")
    def reminders():
        """Email tomorrow's shows to the people going to them.

        Safe to run more often than needed — delivery is idempotent per
        (reader, show), and the lookup window is wider than the interval so a
        missed run recovers on the next one.
        """
        from .services.notifications import send_due_show_reminders

        result = send_due_show_reminders()
        click.echo(
            f"Reminders: {result['sent']} sent from {result['candidates']} candidates."
        )

    @notify.command("preview")
    @click.argument("template")
    @click.option("--out", default="-", help="File to write, or - for stdout.")
    def preview(template: str, out: str):
        """Render an email to HTML without sending it.

        Email templates are the one thing here with no test that can tell you
        it *looks* right, so being able to open one in a browser matters.
        """
        from .services.email_preview import render_preview

        html = render_preview(template)
        if out == "-":
            click.echo(html)
        else:
            from pathlib import Path

            Path(out).write_text(html, encoding="utf-8")
            click.echo(f"Wrote {out}")

    app.cli.add_command(media)
    app.cli.add_command(seed)
    app.cli.add_command(notify)
