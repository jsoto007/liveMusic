"""Demo listings — the prototype's week, as real rows.

Development and test only; ``flask seed demo`` refuses to run anywhere else.
Idempotent: running it twice does not duplicate anything.
"""

from datetime import datetime, time, timedelta, timezone

from .models import (
    AgeRestriction,
    Artist,
    ArtistMember,
    Event,
    EventLineupSlot,
    EventStatus,
    Genre,
    User,
    UserRole,
    Venue,
    utcnow,
)
from .utils.handles import unique_handle
from .utils.passwords import hash_password
from .utils.slugs import unique_slug

TIMEZONE = "America/New_York"

VENUES = [
    ("Dusk", "Olneyville", 41.8180, -71.4460),
    ("Nick-a-Nee's", "Federal Hill", 41.8190, -71.4230),
    ("Columbus Theatre", "West End", 41.8155, -71.4230),
    ("Alchemy", "Downcity", 41.8230, -71.4120),
    ("AS220", "Downcity", 41.8237, -71.4128),
    ("The Parlour", "Smith Hill", 41.8340, -71.4290),
    ("Askew", "Downcity", 41.8225, -71.4155),
    ("Fête Ballroom", "Olneyville", 41.8175, -71.4495),
]

ARTISTS = [
    {
        "name": "Bloodroot Choir",
        "neighborhood": "Olneyville",
        "one_liner": "Post-punk quartet",
        "sounds_like": "Dry drums, ringing open strings, one voice pitched just under the guitars.",
        "bio": (
            "Formed in 2022 out of two bands that broke up the same month. Two records on "
            "Magnolia Tapes, both recorded in a night. They play about twice a month and "
            "always take a local opener."
        ),
        "style_tags": ["Post-punk", "No wave"],
        "available_for_hire": True,
        "members": [
            ("Ada Fournier", "guitar, voice"),
            ("Wes Tamayo", "guitar"),
            ("June Okonkwo", "bass"),
            ("Sam Reyes", "drums"),
        ],
    },
    {
        "name": "The Coleman Trio",
        "neighborhood": "Federal Hill",
        "one_liner": "Standards, two sets",
        "sounds_like": "Piano, upright bass, brushes, and whoever is in town.",
        "bio": "A Tuesday residency going on nine years. No cover, no set list.",
        "style_tags": ["Jazz", "Standards"],
        "available_for_hire": True,
        "members": [("Ernest Coleman", "piano")],
    },
    {
        "name": "Kestrel",
        "neighborhood": "Olneyville",
        "one_liner": "Room for six hundred and it will fill",
        "sounds_like": "Big rooms, bigger chorus.",
        "bio": "First hometown show since the record.",
        "style_tags": ["Rock", "Art rock"],
        "available_for_hire": False,
        "members": [],
    },
]

# (headline, artist name or None, venue name, day offset, hour, minute, genre,
#  price cents, ages, support line, short line, blurb)
EVENTS = [
    (
        "Bloodroot Choir", "Bloodroot Choir", "Dusk", 0, 21, 0, Genre.ROCK_PUNK, 1200,
        AgeRestriction.TWENTY_ONE_PLUS,
        "w/ Slow Vane and Cassette Weather",
        "Two guitars, no chorus pedal, a room that sweats.",
        "Four years in the same practice room on Magnolia Street and they still play like "
        "the lease is up. The new songs are slower and meaner.",
    ),
    (
        "The Coleman Trio", "The Coleman Trio", "Nick-a-Nee's", 0, 19, 30, Genre.JAZZ, 0,
        AgeRestriction.TWENTY_ONE_PLUS,
        "Standards, two sets",
        "Standards until the room thins out. Tip the bucket.",
        "A Tuesday residency going on nine years. Ernest Coleman on piano, whoever is in "
        "town on bass and brushes. No cover, no set list, and the kitchen stays open.",
    ),
    (
        "Providence Sinfonia", None, "Columbus Theatre", 0, 20, 0, Genre.CLASSICAL, 2800,
        AgeRestriction.ALL_AGES,
        "Ravel and Florence Price",
        "Le Tombeau de Couperin and the Third Symphony.",
        "Forty players in a room built for vaudeville. Ravel first, then Price's Third — "
        "the juba movement is the reason to come.",
    ),
    (
        "Vault Sessions: DJ Amaru", None, "Alchemy", 0, 23, 0, Genre.ELECTRONIC, 1500,
        AgeRestriction.TWENTY_ONE_PLUS,
        "w/ Nine Fathoms, resident sets",
        "House and broken beat until two.",
        "Monthly night in the basement room. Amaru plays long — three hours, mostly "
        "records — with Nine Fathoms warming up.",
    ),
    (
        "Open Mic at AS220", None, "AS220", 1, 19, 0, Genre.OPEN_MIC, 0,
        AgeRestriction.ALL_AGES,
        "Sign-up at six",
        "Five minutes or two songs, whichever ends first.",
        "The most forgiving room in the city. Sign-up sheet goes on the wall at six and "
        "fills by half past. House amp, house kit, bring your own cable.",
    ),
    (
        "Marisol & the Long Way", None, "The Parlour", 1, 20, 30, Genre.FOLK_COUNTRY, 1000,
        AgeRestriction.TWENTY_ONE_PLUS,
        "w/ Bell Hollow",
        "Pedal steel, close harmony, a short bar.",
        "Marisol Vega writes the kind of songs that end on the wrong chord and mean it.",
    ),
    (
        "Iron Vespers", None, "Askew", 3, 21, 0, Genre.METAL, 1800,
        AgeRestriction.EIGHTEEN_PLUS,
        "w/ Gravecoat, Slow Vane",
        "Doom, three bands, earplugs at the door.",
        "Two guitars tuned to C and a drummer who plays behind everything. Askew hands "
        "out plugs at the door and you should take them.",
    ),
    (
        "Kestrel", "Kestrel", "Fête Ballroom", 4, 20, 0, Genre.ROCK_PUNK, 2200,
        AgeRestriction.ALL_AGES,
        "w/ Bloodroot Choir",
        "Room for six hundred and it will fill.",
        "First hometown show since the record. The ballroom holds six hundred and this "
        "will sell through the week.",
    ),
]

LINEUPS = {
    "Bloodroot Choir": [
        ("Cassette Weather", "tape loops, solo", 0),
        ("Slow Vane", "noise rock, Pawtucket", 50),
        ("Bloodroot Choir", "headline", 100),
    ],
    "Kestrel": [
        ("Bloodroot Choir", "support", 0),
        ("Kestrel", "headline", 75),
    ],
}


def seed_demo_data(session, *, city: str = "Providence") -> dict:
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(TIMEZONE)
    today_local = utcnow().astimezone(zone).date()

    demo_user = session.query(User).filter(User.email == "band@example.com").one_or_none()
    if demo_user is None:
        demo_user = User(
            email="band@example.com",
            password_hash=hash_password("demo-password-1234"),
            display_name="Ada Fournier",
            handle=unique_handle(session, "ada_fournier"),
            home_city=city,
            role=UserRole.ARTIST,
        )
        session.add(demo_user)
        session.flush()

    venues: dict[str, Venue] = {}
    for name, neighborhood, latitude, longitude in VENUES:
        venue = session.query(Venue).filter(Venue.name == name, Venue.city == city).one_or_none()
        if venue is None:
            venue = Venue(
                name=name,
                slug=unique_slug(session, Venue, f"{name}-{city}"),
                city=city,
                neighborhood=neighborhood,
                latitude=latitude,
                longitude=longitude,
                timezone_name=TIMEZONE,
            )
            session.add(venue)
            session.flush()
        venues[name] = venue

    artists: dict[str, Artist] = {}
    for spec in ARTISTS:
        artist = session.query(Artist).filter(Artist.name == spec["name"]).one_or_none()
        if artist is None:
            artist = Artist(
                owner_user_id=demo_user.id,
                name=spec["name"],
                slug=unique_slug(session, Artist, spec["name"]),
                city=city,
                neighborhood=spec["neighborhood"],
                one_liner=spec["one_liner"],
                sounds_like=spec["sounds_like"],
                bio=spec["bio"],
                style_tags=spec["style_tags"],
                available_for_hire=spec["available_for_hire"],
                verified_at=utcnow(),
            )
            session.add(artist)
            session.flush()
            for position, (member_name, instrument) in enumerate(spec["members"]):
                session.add(
                    ArtistMember(
                        artist_id=artist.id,
                        name=member_name,
                        instrument=instrument,
                        position=position,
                    )
                )
        artists[spec["name"]] = artist

    created_events = 0
    for (
        headline, artist_name, venue_name, day_offset, hour, minute, genre,
        price_cents, ages, support, short_line, blurb,
    ) in EVENTS:
        venue = venues[venue_name]
        local_start = datetime.combine(
            today_local + timedelta(days=day_offset), time(hour, minute), tzinfo=zone
        )
        starts_at = local_start.astimezone(timezone.utc)

        existing = (
            session.query(Event)
            .filter(Event.headline == headline, Event.venue_id == venue.id)
            .one_or_none()
        )
        if existing is not None:
            continue

        event = Event(
            artist_id=artists[artist_name].id if artist_name else None,
            venue_id=venue.id,
            created_by_user_id=demo_user.id,
            headline=headline,
            support_line=support,
            genre=genre,
            starts_at=starts_at,
            doors_at=starts_at - timedelta(minutes=30),
            price_cents=price_cents,
            age_restriction=ages,
            short_line=short_line,
            blurb=blurb,
            status=EventStatus.PUBLISHED,
            published_at=utcnow(),
        )
        session.add(event)
        session.flush()

        for position, (slot_name, note, offset_minutes) in enumerate(
            LINEUPS.get(headline, [])
        ):
            session.add(
                EventLineupSlot(
                    event_id=event.id,
                    name=slot_name,
                    note=note,
                    starts_at=starts_at + timedelta(minutes=offset_minutes),
                    position=position,
                )
            )
        created_events += 1

    session.commit()
    return {"venues": len(venues), "artists": len(artists), "events": created_events}
