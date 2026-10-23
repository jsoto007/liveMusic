"""The 2 September 2026 listings batch: shape, sourcing, isolation and idempotency.

Same standard as the three `test_seed_real_nyc_music_rooms*` files before it.
The seed data is hand-transcribed from published venue calendars, so the
assertions here are aimed at what a careless edit breaks silently — a headline
past the column width, a venue name that no longer matches the `VENUES` table,
two rows that collide on the idempotency key, a row that drifted outside the
advertised window, or a re-run that duplicates the batch instead of no-opping.

Four tests are specific to this pass, and each pins a sourcing decision the
module docstring makes explicitly, so that flattening one is a test failure
rather than a quiet misreport:

* `test_drom_rows_carry_a_door_time_because_that_is_all_drom_publishes` —
  Drom's calendar prints "Doors: 6:30 PM" and no set time, so a Drom row holds
  the same instant in `starts_at` and `doors_at`. The single exception is the
  Danielle Nicole row, whose ticketing page publishes both.
* `test_only_a_published_door_policy_earns_a_21_plus_row` — `age_restriction`
  is NOT NULL, so every row must claim something. Exactly one source in this
  batch states a policy.
* `test_the_free_rooms_are_free_and_the_rest_are_unknown` — Culture Lab says
  "Always free", Drom bills one night free with RSVP, and everything else is
  NULL. Free and unknown render differently and must not drift together.
* `test_every_roulette_row_prints_the_price_roulette_prints` — Roulette is the
  one room here that publishes a figure beside a date; nine of its ten in-window
  listings are in, and only the memorial night lacks a price.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.extensions import db
from app.models import AgeRestriction, Event, EventStatus, Genre, Venue
from scripts.seed_real_nyc import VENUES as VENUES_CONCERT_TIER
from scripts.seed_real_nyc_bars import VENUES as VENUES_BAR_TIER
from scripts.seed_real_nyc_music_rooms import VENUES as VENUES_MUSIC_ROOMS
from scripts.seed_real_nyc_music_rooms_2 import VENUES as VENUES_MUSIC_ROOMS_2
from scripts.seed_real_nyc_music_rooms_3 import VENUES as VENUES_MUSIC_ROOMS_3
from scripts.seed_real_nyc_music_rooms_4 import (
    EVENTS,
    TIMEZONE,
    VENUES,
    seed_real_nyc_music_rooms_4,
)

# The window the batch's docstring promises. A row outside it is either a typo
# or a stale copy-paste from one of the earlier passes.
WINDOW_START = datetime(2026, 9, 2, tzinfo=ZoneInfo(TIMEZONE))
WINDOW_END = datetime(2026, 11, 1, tzinfo=ZoneInfo(TIMEZONE))


def test_every_event_names_a_venue_the_script_creates():
    for headline, venue_name, *_rest in EVENTS:
        assert venue_name in VENUES, f"{headline!r} points at unknown venue {venue_name!r}"


def test_no_venue_is_declared_without_a_listing():
    booked = {venue_name for _headline, venue_name, *_rest in EVENTS}
    assert booked == set(VENUES), "VENUES and EVENTS disagree about which rooms are in"


def test_this_batch_introduces_only_rooms_the_earlier_passes_missed():
    already_seeded = (
        set(VENUES_CONCERT_TIER)
        | set(VENUES_BAR_TIER)
        | set(VENUES_MUSIC_ROOMS)
        | set(VENUES_MUSIC_ROOMS_2)
        | set(VENUES_MUSIC_ROOMS_3)
    )
    overlap = set(VENUES) & already_seeded
    assert not overlap, f"these rooms are already in the paper: {sorted(overlap)}"


def test_this_pass_reaches_four_boroughs_and_admits_the_fifth_is_missing():
    # This batch reaches Manhattan, Brooklyn, Queens and the Bronx. Staten
    # Island is absent for the second pass running: the only room there that
    # publishes a readable dated calendar is the St. George Theatre, and the
    # second pass already seeded it. The gap is deliberate and documented, and
    # this test exists so a later editor reads it as a known hole rather than
    # an oversight — and so that adding a Staten Island room to this file
    # forces the docstring and the report to be updated too.
    addresses = " | ".join(address for _hood, address, *_coords in VENUES.values())
    for present in ("New York, NY", "Brooklyn, NY", "Long Island City, NY", "Bronx, NY"):
        assert present in addresses, f"this pass no longer reaches {present!r}"
    assert "Staten Island, NY" not in addresses, (
        "this pass now reaches Staten Island — update the module docstring and "
        "the report, which both say it does not"
    )


def test_text_fits_the_columns_it_is_stored_in():
    for (
        headline, _venue, _dt, _genre, _price, _ages, support, short_line, blurb,
        url, _doors,
    ) in EVENTS:
        assert 0 < len(headline) <= 160, headline
        assert support is None or len(support) <= 300, headline
        assert short_line is None or len(short_line) <= 300, headline
        assert blurb is None or blurb.strip(), headline
        assert url is None or len(url) <= 500, headline


def test_every_row_is_a_valid_enum_and_a_sane_price():
    for headline, _venue, _dt, genre, price, ages, *_rest in EVENTS:
        assert isinstance(genre, Genre), headline
        assert isinstance(ages, AgeRestriction), headline
        # Money is integer cents. A free show is 0; "unknown/varies" is None.
        assert price is None or (isinstance(price, int) and price >= 0), headline
        assert not isinstance(price, bool), headline


def test_drom_rows_carry_a_door_time_because_that_is_all_drom_publishes():
    drom = [row for row in EVENTS if row[1] == "Drom"]
    assert drom, "the Drom rows have gone missing"

    for headline, _venue, local_dt, *_middle, doors in drom:
        assert doors is not None, f"{headline!r} lost the door time Drom publishes"
        assert doors <= local_dt, f"{headline!r} opens its doors after it starts"
        assert "Doors" in _middle[3], (
            f"{headline!r} no longer tells the reader its time is a door time"
        )

    # Exactly one Drom listing publishes a set time as well as a door time, so
    # exactly one Drom row may have the two columns disagree.
    split = {row[0] for row in drom if row[-1] != row[2]}
    assert split == {"Danielle Nicole"}, split


def test_only_a_published_door_policy_earns_a_21_plus_row():
    # age_restriction is NOT NULL, so every row claims something. A row claims
    # 21+ only where a source says so — one row, in this batch.
    restricted = {row[0] for row in EVENTS if row[5] is AgeRestriction.TWENTY_ONE_PLUS}
    assert restricted == {"Danielle Nicole"}, restricted
    assert not [row for row in EVENTS if row[5] is AgeRestriction.EIGHTEEN_PLUS]


def test_the_free_rooms_are_free_and_the_rest_are_unknown():
    # Culture Lab's own page: Sunset Jazz is "Always free and open to the
    # community". Every Sunset Jazz row is a real zero.
    sunset = [row for row in EVENTS if row[0].startswith("Sunset Jazz:")]
    assert len(sunset) == 9, f"Sunset Jazz has {len(sunset)} rows"
    assert all(row[4] == 0 for row in sunset), "a Sunset Jazz row lost its free price"

    # Beyond the series, exactly one row in the batch is billed free.
    free = {row[0] for row in EVENTS if row[4] == 0}
    assert free - {row[0] for row in sunset} == {"The Petty Toms"}

    # Lehman publishes a Ticketmaster link and no figure, so unknown, not free.
    lehman = [row for row in EVENTS if row[1] == "Lehman Center for the Performing Arts"]
    assert lehman, "the Lehman Center rows have gone missing"
    assert all(row[4] is None for row in lehman), (
        "a Lehman row claims a price the hall does not publish"
    )


def test_every_roulette_row_prints_the_price_roulette_prints():
    roulette = {row[0]: row[4] for row in EVENTS if row[1] == "Roulette Intermedium"}
    assert len(roulette) == 9, f"Roulette has {len(roulette)} rows"
    priced = [price for price in roulette.values() if price is not None]
    assert len(priced) == 8, "a Roulette price went missing"
    assert set(priced) == {2500, 3500, 4000}, sorted(set(priced))
    # The memorial night is the one Roulette listing with no printed price.
    unpriced = [head for head, price in roulette.items() if price is None]
    assert unpriced == ["Sō Laboratories in Memory of Tim Thomas"], unpriced


def test_every_listing_is_sourced_to_a_published_page():
    for headline, _venue, _dt, _genre, _price, _ages, _support, _short, _blurb, url, _d in EVENTS:
        assert url and url.startswith("https://"), f"{headline!r} has no source URL"


def test_the_idempotency_key_is_actually_unique():
    keys = [(headline, venue, dt) for headline, venue, dt, *_rest in EVENTS]
    duplicates = {k for k in keys if keys.count(k) > 1}
    assert not duplicates, f"rows collide on (headline, venue, starts_at): {duplicates}"


def test_every_listing_falls_inside_the_advertised_window():
    zone = ZoneInfo(TIMEZONE)
    for headline, _venue, local_dt, *_rest in EVENTS:
        aware = local_dt.replace(tzinfo=zone)
        assert WINDOW_START <= aware < WINDOW_END, f"{headline!r} at {aware.isoformat()}"


def test_the_friday_series_lands_on_fridays_except_the_night_it_admits():
    # Culture Lab bills Sunset Jazz as "every Friday at 8 PM" and then dates one
    # of them 10 October, a Saturday. The published date is used as published
    # and the exception is named here, so a later editor cannot silently add a
    # second off-Friday night without this test noticing.
    off_friday = set()
    for headline, _venue, local_dt, *_rest in EVENTS:
        if not headline.startswith("Sunset Jazz:"):
            continue
        assert local_dt.hour == 20 and local_dt.minute == 0, headline
        if local_dt.weekday() != 4:
            off_friday.add(headline)
    assert off_friday == {"Sunset Jazz: Keith Jordan"}, off_friday


def test_the_coltrane_centennial_falls_on_coltranes_hundredth_birthday():
    # Sistas' Place's own page calls 23 September 2026 a Saturday; it is a
    # Wednesday, and it is the centenary of Coltrane's birth to the day, which
    # its Eventbrite listing confirms. If this row ever drifts to the Saturday
    # the whole point of the booking is gone.
    row = next(row for row in EVENTS if row[0].startswith("James Carter Quintet"))
    assert row[2].date() == datetime(2026, 9, 23).date()
    assert row[2].weekday() == 2, "23 September 2026 is a Wednesday"
    assert row[1] == "Janes United Methodist Church", (
        "the centennial is filed under the room the music is in, not the presenter"
    )


def test_seeding_publishes_the_batch_and_re_running_adds_nothing(app):
    with app.app_context():
        first = seed_real_nyc_music_rooms_4(db.session)
        assert first["venues"] == len(VENUES)
        assert first["events"] == len(EVENTS)

        second = seed_real_nyc_music_rooms_4(db.session)
        assert second["events"] == 0
        assert db.session.query(Event).count() == len(EVENTS)
        assert db.session.query(Venue).count() == len(VENUES)


def test_seeded_events_are_published_with_utc_instants_and_a_venue_zone(app):
    with app.app_context():
        seed_real_nyc_music_rooms_4(db.session)

        for event in db.session.query(Event).all():
            assert event.status is EventStatus.PUBLISHED
            assert event.published_at is not None
            assert event.venue.timezone_name == TIMEZONE
            assert event.poster_key is None

        # Spot-check that a wall-clock time survived the round trip into UTC:
        # Sunset Jazz is billed at 8pm, which is 00:00 UTC the next day in EDT.
        sunset = (
            db.session.query(Event)
            .filter(Event.headline == "Sunset Jazz: Federico Foli Trio")
            .one()
        )
        stored = sunset.starts_at
        # SQLite hands back a naive datetime; Postgres an aware UTC one. Both
        # hold the same instant, so normalise before comparing rather than
        # letting astimezone() read the naive value as server-local time.
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        assert stored.astimezone(timezone.utc).hour == 0
        local = stored.astimezone(ZoneInfo(TIMEZONE))
        assert (local.hour, local.minute, local.weekday()) == (20, 0, 4)


def test_the_one_split_door_time_survives_the_round_trip(app):
    with app.app_context():
        seed_real_nyc_music_rooms_4(db.session)
        zone = ZoneInfo(TIMEZONE)

        event = db.session.query(Event).filter(Event.headline == "Danielle Nicole").one()
        for column, expected in ((event.starts_at, (19, 0)), (event.doors_at, (18, 30))):
            stored = column if column.tzinfo else column.replace(tzinfo=timezone.utc)
            local = stored.astimezone(zone)
            assert (local.hour, local.minute) == expected


@pytest.mark.parametrize("field", ["latitude", "longitude"])
def test_every_venue_carries_coordinates_inside_the_city(field):
    bounds = {"latitude": (40.47, 40.92), "longitude": (-74.30, -73.68)}
    low, high = bounds[field]
    index = {"latitude": 2, "longitude": 3}[field]
    for name, row in VENUES.items():
        value = row[index]
        assert low <= value <= high, f"{name} {field}={value} is outside New York City"
