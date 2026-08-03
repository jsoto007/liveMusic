"""Render an email with plausible data, without sending it.

Templates are the one part of this codebase a test cannot really validate — a
suite can prove the HTML renders, not that it *reads* well or survives
Outlook. `flask notify preview show_reminder --out /tmp/x.html` gives you
something to open.
"""

from datetime import timedelta
from types import SimpleNamespace

from ..models import utcnow
from .email_service import render_email

_SAMPLE_VENUE = {"name": "Dusk", "neighborhood": "Olneyville", "city": "Providence"}

_SAMPLE_EVENT = {
    "id": "00000000-0000-0000-0000-000000000001",
    "headline": "Bloodroot Choir",
    "genre_label": "Rock & punk",
    "day_label": "Tomorrow",
    "date_long": "Wed, 29 July",
    "time_label": "9:00 PM",
    "doors_label": "8:30 PM",
    "price_label": "$12",
    "age_label": "21+",
    "short_line": "Two guitars, no chorus pedal, a room that sweats.",
    "venue": _SAMPLE_VENUE,
}

_SAMPLE_USER = SimpleNamespace(
    display_name="Ada Fournier", email="ada@example.com", id="00000000-0000-0000-0000-0000000000aa"
)

_SAMPLE_ARTIST = SimpleNamespace(name="Bloodroot Choir", slug="bloodroot-choir")


def render_preview(template: str) -> str:
    context = {
        "user": _SAMPLE_USER,
        "site_url": "https://livemsc.example",
        "unsubscribe_url": "https://livemsc.example/api/v1/email/unsubscribe?user=…&sig=…",
        "verify_url": "https://livemsc.example/verify-email?token=sample",
        "reset_url": "https://livemsc.example/reset-password?token=sample",
        "event_url": "https://livemsc.example/shows/sample",
        "artist_url": "https://livemsc.example/bands/bloodroot-choir",
        "event": _SAMPLE_EVENT,
        "artist": _SAMPLE_ARTIST,
        "ttl_hours": 48,
        "ttl_minutes": 30,
        "now": utcnow() + timedelta(days=1),
    }
    html, _text = render_email(template, **context)
    return html


def available_templates() -> list[str]:
    return [
        "verify_email",
        "reset_password",
        "new_show_from_followed",
        "show_reminder",
    ]
