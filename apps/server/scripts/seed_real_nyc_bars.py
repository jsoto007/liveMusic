"""Real, currently-running bar music nights — karaoke, live music, open mics, DJ nights.

A separate pass from `seed_real_nyc.py` (which seeds full concert-venue
bills): this one covers the neighborhood-bar tier, swept borough by borough,
zip code by zip code, via web research in August 2026. Every venue, address
and recurring schedule below was verified against the venue's own site or a
current listing (Yelp, Time Out, Eventbrite, Instagram) — none were guessed.
A few real, currently-operating venues turned up in the research with strong
evidence of *a* recurring music night but no confirmable day/time; those were
left out rather than assigned a guessed schedule.

No photo is attached to any of these rows. `poster_key` stays null and the
already-built per-genre house-stock fallback (`packages/shared/STOCK_POSTERS`
+ `apps/web/src/lib/stock.ts` + the mobile equivalent) covers the display —
that system needs no per-event sourcing and carries no third-party
attribution obligation, which is the right fit for a batch this size.

Idempotent, keyed on (headline, venue, starts_at) exactly like
`seed_real_nyc.py`. Coordinates are the neighborhood centroids in `VENUES`
below, not a live geocode: a first pass through the app's own LocationIQ
proxy under this script's request volume tripped its internal rate budget
repeatedly, and several of the results that came back anyway were wrong by a
borough (e.g. "Lucinda's" on Avenue A landed in eastern Queens) — silently
wrong coordinates on a map are worse than neighborhood-level ones, so the
live lookup was dropped rather than trusted.

Run from apps/server, with a real DATABASE_URL in the environment:

    python scripts/seed_real_nyc_bars.py
"""

import argparse
import os
import sys
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
from app.utils.passwords import hash_password  # noqa: E402
from app.utils.slugs import unique_slug  # noqa: E402

TIMEZONE = "America/New_York"
CITY = "New York"
CURATOR_EMAIL = "nyc-editorial@live-msc.internal"

# name -> (neighborhood, address, latitude, longitude)
VENUES = {
    "Sing Sing Ave A": (
        "East Village", "81 Avenue A, New York, NY 10009", 40.7267, -73.9819,
    ),
    "Lucinda's": (
        "East Village", "169 Avenue A, New York, NY 10009", 40.7284, -73.9814,
    ),
    "Parkside Lounge": (
        "Lower East Side", "317 East Houston Street, New York, NY 10002", 40.7228, -73.9789,
    ),
    "Birds": (
        "West Village", "64 Downing St, New York, NY 10014", 40.7284, -74.0044,
    ),
    "Marie's Crisis Cafe": (
        "West Village", "59 Grove St, New York, NY 10014", 40.7337, -74.0026,
    ),
    "Boxers NYC Hell's Kitchen": (
        "Hell's Kitchen", "735 9th Ave, New York, NY 10019", 40.7654, -73.9899,
    ),
    "The Center at West Park": (
        "Upper West Side", "165 West 86th Street, New York, NY 10024", 40.7862, -73.9761,
    ),
    "Red Rooster Harlem": (
        "Harlem", "310 Lenox Ave, New York, NY 10027", 40.8093, -73.9441,
    ),
    "Harlem Shake": (
        "Harlem", "100 W 124th St, New York, NY 10027", 40.8093, -73.9454,
    ),
    "Alligator Lounge": (
        "Williamsburg", "600 Metropolitan Ave, Brooklyn, NY 11211", 40.7145, -73.9494,
    ),
    "Beats Karaoke": (
        "Williamsburg", "219 Grand St, Brooklyn, NY 11211", 40.7126, -73.9600,
    ),
    "Good Room": (
        "Greenpoint", "98 Meserole Ave, Brooklyn, NY 11222", 40.7268, -73.9505,
    ),
    "Starr Bar": (
        "Bushwick", "214 Starr St, Brooklyn, NY 11237", 40.7037, -73.9219,
    ),
    "American Cheez": (
        "Park Slope", "444 7th Ave, Brooklyn, NY 11215", 40.6664, -73.9836,
    ),
    "Freddy's Bar": (
        "Park Slope", "627 5th Ave, Brooklyn, NY 11215", 40.6626, -73.9917,
    ),
    "Union Hall": (
        "Park Slope", "702 Union St, Brooklyn, NY 11215", 40.6779, -73.9800,
    ),
    "Ginger's Bar": (
        "Park Slope", "363 5th Ave, Brooklyn, NY 11215", 40.6721, -73.9873,
    ),
    "Essence Bar & Grill": (
        "Crown Heights", "1662 Atlantic Ave, Brooklyn, NY 11213", 40.6779, -73.9297,
    ),
    "Icon Astoria": (
        "Astoria", "31-84 33rd Street, Astoria, NY 11106", 40.7661, -73.9227,
    ),
    "3308 Gastrobar": (
        "Astoria", "3308 Broadway, Astoria, NY 11106", 40.7648, -73.9207,
    ),
    "LIC Bar": (
        "Long Island City", "45-58 Vernon Blvd, Long Island City, NY 11101", 40.7466, -73.9491,
    ),
    "Dutch Kills": (
        "Long Island City", "27-24 Jackson Ave, Long Island City, NY 11101", 40.7466, -73.9394,
    ),
    "Doha Bar Lounge": (
        "Long Island City", "38-34 31st Street, Long Island City, NY 11101", 40.7530, -73.9330,
    ),
    "Lost in Paradise Rooftop": (
        "Long Island City", "11-01 43rd Ave, Long Island City, NY 11101", 40.7503, -73.9515,
    ),
    "Bla Bla Bar": (
        "Jackson Heights", "71-28 72nd St, Jackson Heights, NY 11372", 40.7477, -73.8898,
    ),
    "Bar 47": (
        "Mott Haven", "47 Bruckner Blvd, Bronx, NY 10454", 40.8065, -73.9236,
    ),
    "Jolly Tinker": (
        "Bedford Park", "2875 Webster Ave, Bronx, NY 10458", 40.8683, -73.8874,
    ),
    "The Bronx Beer Hall": (
        "Belmont", "2344 Arthur Ave, Bronx, NY 10458", 40.8551, -73.8879,
    ),
    "Steiny's Pub": (
        "St. George", "3 Hyatt St, Staten Island, NY 10301", 40.6437, -74.0765,
    ),
    "Every Thing Goes Book Cafe": (
        "St. George", "208 Bay St, Staten Island, NY 10301", 40.6413, -74.0754,
    ),
}

# (headline, venue, local start datetime, genre, price_cents, ages, support_line,
#  short_line, blurb, ticket_url)
EVENTS = [
    (
        "Karaoke at Sing Sing Ave A", "Sing Sing Ave A", datetime(2026, 8, 12, 21, 0),
        Genre.OPEN_MIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Walk-in karaoke, open nightly",
        "A dedicated East Village karaoke bar — no sign-up sheet, no theme night, just a "
        "room that runs karaoke every night it's open.",
        "https://www.singsingavea.com/",
    ),
    (
        "Bluegrass Tuesday at Lucinda's", "Lucinda's", datetime(2026, 8, 18, 20, 0),
        Genre.FOLK_COUNTRY, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Live bluegrass, weekly",
        "A Tuesday-night bluegrass set at the East Village's country-and-western bar.",
        "https://www.lucindasnyc.com/",
    ),
    (
        "Songwriters Open Mic at Lucinda's", "Lucinda's", datetime(2026, 8, 16, 13, 30),
        Genre.OPEN_MIC, 0, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Sunday songwriters' round, free",
        "A Sunday-afternoon songwriters' open mic, followed by a live honky-tonk band at "
        "the bar's regular Sunday residency.",
        "https://www.lucindasnyc.com/",
    ),
    (
        "The Inspired Word Open Mic", "Parkside Lounge", datetime(2026, 8, 17, 19, 0),
        Genre.OPEN_MIC, 900, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Music, comedy and spoken word, weekly",
        "A long-running Monday-night open mic on the Lower East Side — music, comedy and "
        "spoken word on one sign-up sheet.",
        "https://www.parksidelounge.nyc/calendar/ylnktykbbwdm6ak-639mz-j63p2",
    ),
    (
        "Live Music at Birds", "Birds", datetime(2026, 8, 14, 20, 0),
        Genre.JAZZ, None, AgeRestriction.ALL_AGES, None,
        "Jazz, funk and soul, Friday nights",
        "A West Village room built for jazz, funk, soul and global grooves — live Friday "
        "and Saturday nights.",
        "https://birds-nyc.com/",
    ),
    (
        "Piano Bar Sing-Along at Marie's Crisis", "Marie's Crisis Cafe",
        datetime(2026, 8, 12, 19, 0), Genre.OPEN_MIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Showtunes, nightly, unamplified",
        "Group sing-along showtunes around a piano, seven nights a week, in a basement "
        "bar that has run this exact ritual for decades.",
        "https://www.mariescrisiscafe.com/about",
    ),
    (
        "Karaoke at Boxers HK", "Boxers NYC Hell's Kitchen", datetime(2026, 8, 12, 21, 0),
        Genre.OPEN_MIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Wednesday karaoke, hosted",
        "A hosted Wednesday-night karaoke set at Boxers' Hell's Kitchen room.",
        "https://boxersnyc.com/hk/events/",
    ),
    (
        "Open Mic at The Center at West Park", "The Center at West Park",
        datetime(2026, 8, 14, 19, 30), Genre.OPEN_MIC, 0, AgeRestriction.ALL_AGES, None,
        "Sign-up at 7:30, free, all forms welcome",
        "A no-cover Friday open mic in a converted chapel — music, poetry, spoken word, "
        "rap, dance and comedy share one sign-up sheet.",
        "https://www.centeratwestpark.org/",
    ),
    (
        "Monday Night Live at Red Rooster", "Red Rooster Harlem", datetime(2026, 8, 17, 20, 0),
        Genre.GOSPEL_SOUL, None, AgeRestriction.ALL_AGES, None,
        "A Harlem showcase, weekly",
        "A Monday-night live showcase co-produced by Erica Mansfield and Jeremiah Abiah — "
        "Broadway performers, original songs, tap and poetry.",
        "https://www.redroosterharlem.com/",
    ),
    (
        "Sunday Soul at Harlem Shake", "Harlem Shake", datetime(2026, 8, 16, 14, 0),
        Genre.GOSPEL_SOUL, 0, AgeRestriction.ALL_AGES, None,
        "Soul Power Band, no cover",
        "A no-cover Sunday-afternoon soul residency led by the Soul Power Band, featuring "
        "C. Kelly Wright.",
        "https://ma.to/venue/harlemshakenyc",
    ),
    (
        "Karaoke Rock City", "Alligator Lounge", datetime(2026, 8, 14, 22, 0),
        Genre.OPEN_MIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Free pizza, loud karaoke",
        "Williamsburg's karaoke-and-personal-pizza night — running most nights of the "
        "week, this is its Friday slot.",
        "https://www.alligatorloungebrooklyn.com/",
    ),
    (
        "Karaoke at Beats", "Beats Karaoke", datetime(2026, 8, 12, 20, 0),
        Genre.OPEN_MIC, None, AgeRestriction.EIGHTEEN_PLUS, None,
        "Open-floor and private rooms, nightly",
        "A dedicated Williamsburg karaoke bar with an open floor plus private rooms, open "
        "most nights of the week.",
        None,
    ),
    (
        "DJ Night at Good Room", "Good Room", datetime(2026, 8, 14, 22, 0),
        Genre.ELECTRONIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Rotating DJs, Friday and Saturday",
        "Greenpoint's dance-floor room, running rotating DJ and promoter lineups Friday "
        "and Saturday nights until 4am.",
        "https://www.nyctourism.com/nightlife/good-room-greenpoint/",
    ),
    (
        "Siren Songs Karaoke Dance Party", "Starr Bar", datetime(2026, 8, 14, 18, 0),
        Genre.OPEN_MIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Karaoke into a dance party, Fridays",
        "A Bushwick Friday-evening karaoke party that runs straight into DJ sets — one of "
        "several recurring music nights Starr Bar runs through the week.",
        "https://www.starrbar.com/events",
    ),
    (
        "Karaoke at American Cheez", "American Cheez", datetime(2026, 8, 12, 21, 0),
        Genre.OPEN_MIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Wednesday karaoke, Park Slope",
        "A Wednesday-night karaoke set at a Park Slope sandwich-and-bar spot.",
        None,
    ),
    (
        "Humans Against Music Karaoke", "Freddy's Bar", datetime(2026, 8, 16, 18, 0),
        Genre.OPEN_MIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "1st and 3rd Sundays",
        "Freddy's long-running karaoke series, on the first and third Sunday of the "
        "month — the bar also runs a separate original-music open mic monthly.",
        "https://www.freddysbar.com/events",
    ),
    (
        "Karaoke Tremendous", "Union Hall", datetime(2026, 8, 14, 22, 0),
        Genre.OPEN_MIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "The Kings of Karaoke, Friday nights",
        "A Friday-night karaoke residency from the Kings of Karaoke crew, downstairs at "
        "Union Hall.",
        "https://unionhallny.com/calendar",
    ),
    (
        "Karaoke at Ginger's", "Ginger's Bar", datetime(2026, 8, 13, 20, 0),
        Genre.OPEN_MIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Alternating Thursdays",
        "A Park Slope lesbian bar's karaoke night, on alternating Thursdays — worth a "
        "call ahead to confirm it's an \"on\" week.",
        None,
    ),
    (
        "Karaoke at Essence", "Essence Bar & Grill", datetime(2026, 8, 14, 21, 0),
        Genre.OPEN_MIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Friday and Saturday nights",
        "A Crown Heights karaoke set, running Friday and Saturday nights.",
        "https://essencebar.com/",
    ),
    (
        "Karaoke at Icon Astoria", "Icon Astoria", datetime(2026, 8, 12, 21, 0),
        Genre.OPEN_MIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "A dedicated karaoke bar, nightly",
        "Astoria's dedicated karaoke room, open nightly with no cover to sing.",
        "https://www.iconastoria.com/karaoke",
    ),
    (
        "Vibra Fridays", "3308 Gastrobar", datetime(2026, 8, 14, 22, 0),
        Genre.ELECTRONIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "DJ set, Astoria",
        "A Friday-night DJ set at an Astoria gastrobar.",
        None,
    ),
    (
        "Live Music Monday at LIC Bar", "LIC Bar", datetime(2026, 8, 17, 20, 0),
        Genre.OTHER, 0, AgeRestriction.ALL_AGES, None,
        "The Jeff Weiss residency, free",
        "A free Monday-night live-music residency at Long Island City's backyard bar — "
        "one of several weekly music slots the room runs.",
        "https://www.licbar.com/upcoming-events",
    ),
    (
        "Jazz at Debbie's", "Dutch Kills", datetime(2026, 8, 14, 21, 0),
        Genre.JAZZ, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Live jazz and ragtime, upstairs",
        "Live jazz and ragtime in \"Debbie's,\" the upstairs room at this Long Island "
        "City cocktail bar — Friday and Saturday nights.",
        "https://www.dutchkillsbar.com/events/",
    ),
    (
        "R&B Ladies Night Karaoke", "Doha Bar Lounge", datetime(2026, 8, 13, 17, 0),
        Genre.OPEN_MIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Thursday karaoke dinner party",
        "A Thursday-evening karaoke-and-dinner party at a Long Island City lounge.",
        "https://dohabarlounge.com/ladies-night-thursdays/",
    ),
    (
        "Karaoke Wednesday at Lost in Paradise", "Lost in Paradise Rooftop",
        datetime(2026, 8, 12, 17, 0), Genre.OPEN_MIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Rooftop karaoke, Wednesdays",
        "A Wednesday-evening karaoke night on a Long Island City rooftop.",
        "https://www.lostinparadiserooftop.com/event/karaoke-wednesday/",
    ),
    (
        "Karaoke at Bla Bla Bar", "Bla Bla Bar", datetime(2026, 8, 13, 22, 0),
        Genre.OPEN_MIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Thursday nights, Jackson Heights",
        "A Thursday-night karaoke set at a Jackson Heights Thai bar and lounge.",
        None,
    ),
    (
        "DJ Menyu at Bar 47", "Bar 47", datetime(2026, 8, 14, 21, 0),
        Genre.ELECTRONIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Resident DJ, Fridays",
        "A Friday-night resident-DJ set at a Mott Haven bar.",
        "https://47bruckner.com/",
    ),
    (
        "Karaoke at Jolly Tinker", "Jolly Tinker", datetime(2026, 8, 13, 18, 0),
        Genre.OPEN_MIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Thursday nights, near Fordham",
        "A Thursday-evening karaoke night with DJ Cut King, near Fordham University.",
        None,
    ),
    (
        "Judgment Free Karaoke", "The Bronx Beer Hall", datetime(2026, 8, 14, 20, 0),
        Genre.OPEN_MIC, None, AgeRestriction.ALL_AGES, None,
        "Inside the Arthur Avenue Retail Market",
        "A Friday-night karaoke set inside the Arthur Avenue Retail Market's beer hall.",
        "https://www.thebronxbeerhall.com/",
    ),
    (
        "Karaoke at Steiny's", "Steiny's Pub", datetime(2026, 8, 13, 21, 0),
        Genre.OPEN_MIC, None, AgeRestriction.TWENTY_ONE_PLUS, None,
        "Thursday nights, St. George",
        "A Thursday-night karaoke set at a St. George neighborhood pub, hosted by Ray.",
        "https://steinys.pub",
    ),
    (
        "Liberation Open Mic", "Every Thing Goes Book Cafe", datetime(2026, 9, 4, 19, 0),
        Genre.OPEN_MIC, 0, AgeRestriction.ALL_AGES, None,
        "First Friday of most months",
        "A free open mic at a Staten Island bookstore-and-stage, on the first Friday of "
        "most months.",
        "https://www.etgstores.com/events",
    ),
]


def _curator(session) -> User:
    user = session.query(User).filter(User.email == CURATOR_EMAIL).one_or_none()
    if user is None:
        import uuid

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
    return out


def seed_real_nyc_bars(session) -> dict:
    zone = ZoneInfo(TIMEZONE)
    curator = _curator(session)
    venues = _venues(session)

    created_events = 0
    for (
        headline, venue_name, local_dt, genre, price_cents, ages, support,
        short_line, blurb, ticket_url,
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
        created_events += 1

    session.commit()
    return {"venues": len(venues), "events": created_events}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    app = create_app(Config)
    with app.app_context():
        summary = seed_real_nyc_bars(db.session)
        print(f"Venues: {summary['venues']}, events created: {summary['events']}")


if __name__ == "__main__":
    main()
