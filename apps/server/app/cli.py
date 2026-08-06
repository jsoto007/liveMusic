"""Operator commands: `flask media sweep`, `flask media configure-cors`, `flask seed demo`."""

import json

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

    @media.command("configure-cors")
    @click.option(
        "--origin",
        "extra_origins",
        multiple=True,
        help="Additional allowed origin (repeatable). Use for custom domains.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Print the policy that would be applied without actually applying it.",
    )
    def configure_cors(extra_origins, dry_run):
        """Apply the correct CORS policy to the R2 bucket.

        Run this once after creating the bucket and again whenever the web
        app's origin changes (new deploy suffix, custom domain, etc.).

        The policy allows PUT, GET and HEAD from every origin in FRONTEND_URL
        and CORS_ORIGINS plus any --origin flags given here, and from localhost
        in development.  Without it the browser blocks every upload before a
        single byte leaves the page.

        \\b
        Examples:

          # Apply using the origins already in your config
          flask --app app media configure-cors

          # Preview without touching the bucket
          flask --app app media configure-cors --dry-run

          # Also allow a custom domain you haven't wired into FRONTEND_URL yet
          flask --app app media configure-cors --origin https://livemsc.example.com
        """
        from botocore.exceptions import BotoCoreError, ClientError

        from .security import parse_origins
        from .services.r2_storage import build_client

        client = build_client()
        if client is None:
            raise click.ClickException(
                "R2 is not configured. Set R2_ACCOUNT_ID (or R2_ENDPOINT_URL), "
                "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and R2_BUCKET, then retry."
            )

        origins = list(parse_origins(app))
        for o in extra_origins:
            cleaned = o.strip().rstrip("/")
            if cleaned and cleaned not in origins:
                origins.append(cleaned)

        if not origins:
            raise click.ClickException(
                "No origins found. Set FRONTEND_URL (or CORS_ORIGINS) in your "
                "environment, or pass --origin https://your-web-app-url."
            )

        bucket = app.config["R2_BUCKET"]
        # R2 uses presigned PUT (not POST — R2 returns 501 on presigned POST).
        # AllowedHeaders must include Content-Type because the presigned
        # signature pins it; omitting it makes the preflight fail even when the
        # origin is allowed.
        policy = [
            {
                "AllowedOrigins": origins,
                "AllowedMethods": ["PUT", "GET", "HEAD"],
                "AllowedHeaders": ["Content-Type"],
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 3600,
            }
        ]

        click.echo(f"CORS policy for bucket '{bucket}':")
        click.echo(json.dumps(policy, indent=2))

        if dry_run:
            click.echo("\n(dry run — policy was NOT applied)")
            return

        try:
            client.put_bucket_cors(
                Bucket=bucket,
                CORSConfiguration={"CORSRules": policy},
            )
        except (ClientError, BotoCoreError) as exc:
            raise click.ClickException(f"Failed to apply CORS policy: {exc}") from exc

        click.echo(f"\nCORS policy applied to '{bucket}'. Uploads should now work.")

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
