"""Real, currently-scheduled NYC shows — not fixture data.

Unlike ``app/seed.py`` (a fictional week of Providence listings gated to
dev/test), this populates the live database with real venues and real events,
each sourced from the venue's own calendar or a major ticketing aggregator in
August 2026. It is meant to be run once, against production, and is written
idempotent (keyed on headline + venue + start time) so a second run is a
no-op rather than a duplicate.

Each event gets its own original stock-style editorial photograph, generated
for that exact bill rather than borrowed from an unrelated artist or assigned
only by genre. The checked-in JPEGs contain no performer likenesses, logos or
promotional artwork. They upload straight to R2 through the server-side seed
path.

Run from apps/server, with a real DATABASE_URL and real R2_* credentials in
the environment:

    python scripts/seed_real_nyc.py
"""

import argparse
import mimetypes
import os
import sys
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (  # noqa: E402
    AgeRestriction,
    Event,
    EventStatus,
    Genre,
    User,
    UserRole,
    Venue,
    utcnow,
)
from app.services.r2_storage import R2Storage, build_client  # noqa: E402
from app.utils.passwords import hash_password  # noqa: E402
from app.utils.slugs import unique_slug  # noqa: E402

TIMEZONE = "America/New_York"
CITY = "New York"
CURATOR_EMAIL = "nyc-editorial@live-msc.internal"

VENUES = {
    "SummerStage (Rumsey Playfield)": (
        "Central Park", "Rumsey Playfield, mid-park at E 72nd St", 40.772778, -73.970186,
    ),
    "SOB's": ("Hudson Square", "204 Varick St", 40.7285, -74.0064),
    "Elsewhere": ("Bushwick", "599 Johnson Ave", 40.7057, -73.9334),
    "Gramercy Theatre": ("Gramercy", "127 E 23rd St", 40.7391, -73.9847),
    "Bryant Park": ("Midtown", "behind the NYPL, 42nd St & 6th Ave", 40.7536, -73.9832),
    "Village Vanguard": ("Greenwich Village", "178 7th Ave S", 40.7351, -74.0027),
    "Bowery Palace": ("East Village", "327 Bowery", 40.7256, -73.9917),
    "Astoria Park": ("Astoria", "Hoyt Ave N & 19th St, under the RFK Bridge", 40.7794, -73.9214),
}

# (headline, venue, local start datetime, genre, price_cents, ages, support_line,
#  short_line, blurb, ticket_url, photo_file)
EVENTS = [
    (
        "Simple Plan / 3OH!3 / Bowling for Soup", "SummerStage (Rumsey Playfield)",
        datetime(2026, 8, 19, 18, 0), Genre.ROCK_PUNK, None, AgeRestriction.ALL_AGES,
        None, "Three 2000s pop-punk headliners, one bill",
        "A benefit-ticketed triple bill at Rumsey Playfield — Simple Plan, 3OH!3 and "
        "Bowling for Soup sharing one stage in Central Park.",
        "https://www.centralpark.com/things-to-do/concerts/summerstage-festival/",
        "simple-plan-triple-bill.jpg",
    ),
    (
        "Andrew Bird with Wordless Music Orchestra", "SummerStage (Rumsey Playfield)",
        datetime(2026, 8, 6, 20, 0), Genre.FOLK_COUNTRY, 0, AgeRestriction.ALL_AGES,
        None, "20th-anniversary set, free at Rumsey Playfield",
        "Andrew Bird marks twenty years of playing SummerStage with the Wordless Music "
        "Orchestra behind him. Free, first-come.",
        "https://www.centralpark.com/things-to-do/concerts/summerstage-festival/",
        "andrew-bird-orchestra.jpg",
    ),
    (
        "Funk Flex Birthday R&B Picnic", "SummerStage (Rumsey Playfield)",
        datetime(2026, 8, 7, 19, 0), Genre.GOSPEL_SOUL, 0, AgeRestriction.ALL_AGES,
        "Jon B, Fonda Rae, Taana Gardner and more",
        "Funk Flex's birthday picnic, free in the park",
        "A free afternoon-into-evening of classic soul and R&B at Rumsey Playfield, "
        "built around Funk Flex's annual birthday picnic.",
        "https://www.centralpark.com/things-to-do/concerts/summerstage-festival/",
        "funk-flex-rnb-picnic.jpg",
    ),
    (
        "Chance the Rapper — Coloring Book 10 Year Anniversary", "SummerStage (Rumsey Playfield)",
        datetime(2026, 8, 18, 19, 0), Genre.HIP_HOP, None, AgeRestriction.ALL_AGES,
        None, "Coloring Book, ten years on",
        "A benefit-ticketed Rumsey Playfield show marking ten years of Coloring Book.",
        "https://www.centralpark.com/things-to-do/concerts/summerstage-festival/",
        "chance-coloring-book.jpg",
    ),
    (
        "The Diplomats: Double Trouble Album Release Concert", "SOB's",
        datetime(2026, 8, 27, 19, 0), Genre.HIP_HOP, None, AgeRestriction.TWENTY_ONE_PLUS,
        None, "Album release show, 21+",
        "The Diplomats celebrate the release of Double Trouble on SOB's main floor.",
        "https://sobs.com/calendar/", "diplomats-album-release.jpg",
    ),
    (
        "Blues Traveler / Gin Blossoms / Spin Doctors", "SummerStage (Rumsey Playfield)",
        datetime(2026, 8, 15, 18, 0), Genre.OTHER, None, AgeRestriction.ALL_AGES,
        None, "A 90s radio-rock triple bill, benefit-ticketed",
        "Three 90s alt-rock radio staples on one Rumsey Playfield bill, ticketed as a "
        "SummerStage benefit night.",
        "https://www.centralpark.com/things-to-do/concerts/summerstage-festival/",
        "blues-traveler-triple-bill.jpg",
    ),
    (
        "Rival Consoles", "Elsewhere",
        datetime(2026, 8, 27, 19, 0), Genre.ELECTRONIC, None, AgeRestriction.ALL_AGES,
        "Arushi Jain (DJ set)", "Live electronic, The Hall",
        "Rival Consoles plays The Hall at Elsewhere with an Arushi Jain DJ set opening.",
        "https://www.elsewhere.club/events", "rival-consoles.jpg",
    ),
    (
        "Hypocrisy", "Gramercy Theatre",
        datetime(2026, 8, 12, 19, 0), Genre.METAL, None, AgeRestriction.ALL_AGES,
        None, "Death metal at the Gramercy",
        "Swedish death metal veterans Hypocrisy headline the Gramercy Theatre.",
        "https://www.livenation.com/event/k7vGF_GNTg40Y/hypocrisy", "hypocrisy-death-metal.jpg",
    ),
    (
        "New York Guitar Festival", "Bryant Park",
        datetime(2026, 8, 14, 19, 0), Genre.CLASSICAL, 0, AgeRestriction.ALL_AGES,
        None, "Free guitar-centred evening on the lawn",
        "An evening of classical, jazz and world guitar repertoire on the Bryant Park "
        "lawn — free, no reservation, as every Picnic Performance is.",
        "https://bryantpark.org/activities/picnic-performances", "new-york-guitar-festival.jpg",
    ),
    (
        "10 Years of Blonde: A Live Jazz Tribute to Frank Ocean", "SOB's",
        datetime(2026, 8, 19, 18, 30), Genre.JAZZ, None, AgeRestriction.TWENTY_ONE_PLUS,
        None, "A jazz band's read on Blonde, ten years later",
        "A live band reinterprets Frank Ocean's Blonde as a jazz set, ten years after "
        "its release.",
        "https://sobs.com/calendar/", "blonde-jazz-tribute.jpg",
    ),
    (
        "Vanguard Jazz Orchestra", "Village Vanguard",
        datetime(2026, 8, 10, 20, 30), Genre.JAZZ, 2500, AgeRestriction.TWENTY_ONE_PLUS,
        None, "The Monday-night residency, running since 1966",
        "The Vanguard Jazz Orchestra's Monday residency, unbroken since 1966 — cover "
        "charge includes the one-drink minimum the room has always run on.",
        "https://villagevanguard.com", "vanguard-jazz-orchestra.jpg",
    ),
    (
        "End of the Weak Hip-Hop Open Mic", "Bowery Palace",
        datetime(2026, 8, 12, 20, 0), Genre.OPEN_MIC, 0, AgeRestriction.ALL_AGES,
        None, "Sign up, free before 9",
        "A long-running weekly hip-hop open mic, free to get in before 9pm.",
        None, "end-of-the-weak-open-mic.jpg",
    ),
    (
        "2026 NYC Summer Music, Arts & Vendor Festival", "Astoria Park",
        datetime(2026, 8, 14, 10, 0), Genre.FESTIVAL, 0, AgeRestriction.ALL_AGES,
        None, "Three days, free, under the RFK Bridge",
        "A free, family-friendly weekend of live music, local vendors and food "
        "alongside the East River in Astoria Park.",
        "https://www.eventbrite.com/e/2026-nyc-summer-music-arts-vendor-festival-tickets-1992065829521",
        "astoria-summer-festival.jpg",
    ),
]

def _curator(session) -> User:
    user = session.query(User).filter(User.email == CURATOR_EMAIL).one_or_none()
    if user is None:
        user = User(
            email=CURATOR_EMAIL,
            password_hash=hash_password(uuid.uuid4().hex + "Aa1!" * 4),
            display_name="Live Msc Editorial",
            home_city=CITY,
            role=UserRole.ADMIN,
            email_verified_at=utcnow(),
        )
        session.add(user)
        session.flush()
    return user


def _venues(session) -> dict[str, Venue]:
    zone = ZoneInfo(TIMEZONE)
    out = {}
    for name, (neighborhood, address, lat, lon) in VENUES.items():
        venue = session.query(Venue).filter(Venue.name == name, Venue.city == CITY).one_or_none()
        if venue is None:
            venue = Venue(
                name=name,
                slug=unique_slug(session, Venue, f"{name}-{CITY}"),
                address=address,
                city=CITY,
                neighborhood=neighborhood,
                latitude=lat,
                longitude=lon,
                timezone_name=TIMEZONE,
            )
            session.add(venue)
            session.flush()
        out[name] = venue
    del zone
    return out


def _upload_poster(event: Event, photos_dir: str, filename: str) -> bool:
    """Upload a local photo straight to R2 and set ``poster_key``.

    Mirrors the API's own upload path (mint an opaque key, PUT the bytes,
    verify with HEAD before trusting it) but calls R2 directly rather than
    through a presigned URL — this is a server-side data-loading script, not
    a client request, so there is no browser in the loop to hand a signature
    to.
    """
    path = os.path.join(photos_dir, filename)
    if not os.path.isfile(path):
        print(f"  ! missing photo file: {path}", file=sys.stderr)
        return False

    content_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
    key = R2Storage.build_key("events/poster", event.id, content_type, kind="image")
    if key is None:
        print(f"  ! unsupported content type for {filename}: {content_type}", file=sys.stderr)
        return False

    client = build_client()
    if client is None:
        print("  ! R2 is not configured; skipping poster upload.", file=sys.stderr)
        return False

    with open(path, "rb") as fh:
        body = fh.read()

    from app.config import Config as _Config  # local import: config is app-bound

    bucket = os.environ.get("R2_BUCKET") or _Config.R2_BUCKET
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)

    head = R2Storage.head_object(key)
    if head is None or head.get("size_bytes") != len(body):
        print(f"  ! upload verification failed for {filename}", file=sys.stderr)
        return False

    event.poster_key = key
    # Original house stock has no third-party attribution line.
    event.poster_credit = None
    return True


def seed_real_nyc(session, *, photos_dir: str | None) -> dict:
    zone = ZoneInfo(TIMEZONE)
    curator = _curator(session)
    venues = _venues(session)

    created_events = 0
    posters_uploaded = 0
    posters_missing = 0
    for (
        headline, venue_name, local_dt, genre, price_cents, ages, support,
        short_line, blurb, ticket_url, photo_file,
    ) in EVENTS:
        venue = venues[venue_name]
        starts_at = local_dt.replace(tzinfo=zone).astimezone(timezone.utc)

        existing = (
            session.query(Event)
            .filter(Event.headline == headline, Event.venue_id == venue.id,
                    Event.starts_at == starts_at)
            .one_or_none()
        )
        if existing is not None:
            if photos_dir and not existing.poster_key:
                if _upload_poster(existing, photos_dir, photo_file):
                    posters_uploaded += 1
                else:
                    posters_missing += 1
            elif not existing.poster_key:
                posters_missing += 1
            continue

        event = Event(
            artist_id=None,
            venue_id=venue.id,
            created_by_user_id=curator.id,
            headline=headline,
            support_line=support,
            genre=genre,
            starts_at=starts_at,
            price_cents=price_cents,
            age_restriction=ages,
            ticket_url=ticket_url,
            short_line=short_line,
            blurb=blurb,
            status=EventStatus.PUBLISHED,
            published_at=utcnow(),
        )
        session.add(event)
        session.flush()

        if photos_dir:
            if _upload_poster(event, photos_dir, photo_file):
                posters_uploaded += 1
            else:
                posters_missing += 1
        else:
            posters_missing += 1

        created_events += 1

    session.commit()
    return {
        "venues": len(venues),
        "events": created_events,
        "posters_uploaded": posters_uploaded,
        "posters_missing": posters_missing,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--photos-dir",
        default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "seed_photos", "nyc"),
        help="Directory holding the event-matched stock photos.",
    )
    parser.add_argument(
        "--require-posters",
        action="store_true",
        help="Exit unsuccessfully if any seeded event still lacks its poster.",
    )
    args = parser.parse_args()

    app = create_app(Config)
    with app.app_context():
        summary = seed_real_nyc(db.session, photos_dir=args.photos_dir)
        print(
            f"Venues: {summary['venues']}, events created: {summary['events']}, "
            f"posters uploaded: {summary['posters_uploaded']}, "
            f"posters missing: {summary['posters_missing']}"
        )
        if args.require_posters and summary["posters_missing"]:
            raise SystemExit(
                "Poster backfill failed: "
                f"{summary['posters_missing']} seeded events still have no R2 object."
            )


if __name__ == "__main__":
    main()
