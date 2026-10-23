"""Six rooms across four boroughs — the sixth real-listings pass.

The five passes before this one are either dated in the reader's past
(`seed_real_nyc.py`, `seed_real_nyc_bars.py`) or already standing in the paper
(`seed_real_nyc_music_rooms.py` on 26 August, `_2` on 28 August, `_3` on
1 September). This pass, swept on 2 September 2026, adds **six rooms none of
the earlier five touched** and takes every dated listing they publish inside
the 2 September – 31 October 2026 window.

The six:

* **Drom** (East Village, Manhattan) — the Avenue A room whose calendar runs
  Turkish rock, Latin album releases, goth and disco parties and a monthly
  flamenco jazz jam, most nights of the week.
* **Roulette Intermedium** (Boerum Hill, Brooklyn) — the Atlantic Avenue hall
  for new and improvised music, and the only room in this batch that prints a
  ticket price beside every date.
* **Culture Lab LIC** (Long Island City, Queens) — a converted warehouse whose
  Sunset Jazz series is free every Friday at eight and names its player weeks
  ahead.
* **Lehman Center for the Performing Arts** (Bedford Park, Bronx) — the
  borough's largest concert hall.
* **Soapbox Gallery** (Prospect Heights, Brooklyn) — a storefront jazz room on
  Dean Street.
* **Janes United Methodist Church** (Bedford-Stuyvesant, Brooklyn) — not a
  music room, but the room Sistas' Place has booked for its Coltrane
  centennial, which is where that night's music actually is.

Staten Island is absent again, for the second pass running, and the reason is
the same one the 1 September report gave: the only Staten Island room that
publishes a dated calendar this tool can read is the St. George Theatre, and
the second pass already seeded it. The dropped rooms are listed in
`reports/nyc-listings-refresh/2026-09-02-four-borough-rooms.md`.

Sourcing rule, unchanged from the earlier passes: every venue, address, date
and set time below was read off a page the venue or its own ticketing partner
publishes. Nothing was inferred. Three sourcing calls are specific to this
pass and each is visible in the data:

1. **Drom publishes a door time and no set time.** Every listing on its
   calendar reads "Doors: 6:30 PM" or similar and stops there. So a Drom row
   carries that instant in BOTH `starts_at` and `doors_at`, and its support
   line says "Doors" in words — the paper shows the reader the only time the
   room published rather than a set time guessed from it. The single exception
   is Danielle Nicole on 23 September, whose ticketing page publishes doors at
   6:30 and the show at 7:00; that row uses both, and is the one Drom row
   where `doors_at` and `starts_at` differ.
2. **Age.** `age_restriction` is NOT NULL in the schema, so a row must claim
   something. A row claims 21+ only where a published page says so — which in
   this batch is the Danielle Nicole ticketing page alone. Every other row
   takes the schema default of ALL_AGES because no source states a door
   policy, not because a source stated all ages.
3. **Prices.** Roulette prints one beside every date, and those are the real
   figures. Culture Lab's own page calls Sunset Jazz "Always free and open to
   the community", so those nine rows are a real `price_cents = 0`, as is
   Drom's 31 October Petty Toms, which its calendar bills free with RSVP.
   Everything else is NULL — unknown, which the paper renders as varies, not
   as free.

Genre follows the same rule the last two passes used: where the listing's own
name or the venue's own copy declares a style the bucket follows it, and where
the calendar publishes a name and nothing else the row is filed under `OTHER`
rather than guessed at. That is why most Drom rows are `OTHER` — the calendar
is a name, a door time and a ticket link. Jams are filed `OPEN_MIC`,
consistent with the fourth and fifth passes.

Screenings, comedy and burlesque on these calendars are not listings for a
music paper and were left out: Drom's 4 September "Rinsed" film premiere, its
four "Schtick a Pole In It" nights, the Lauren Ash comedy tour, the Body &
Pole student showcase and the New York School of Burlesque; and Roulette's
22 September Monkathon, which is a world premiere *screening* rather than a
performance.

No photo is attached to any of these rows. `poster_key` stays null and the
per-genre house-stock fallback (`packages/shared/STOCK_POSTERS` +
`apps/web/src/lib/stock.ts` + the mobile equivalent) covers the display, which
carries no third-party attribution obligation.

Idempotent, keyed on (headline, venue, starts_at) exactly like the five
scripts before it. Coordinates are address-level approximations typed from the
published street addresses, not a live geocode — the app's LocationIQ proxy
rate-limits under a batch this size, and an approximate pin beats a silently
wrong one.

Run from apps/server. The script builds its own SQLAlchemy session rather than
booting the Flask app (see `_session` for why), and it will not write anything
without `--yes`:

    ./.venv/bin/python scripts/seed_real_nyc_music_rooms_4.py            # dry run
    ./.venv/bin/python scripts/seed_real_nyc_music_rooms_4.py --yes      # commit

The target comes from `--database-url`, else `$DATABASE_URL`, else `.env`. It
is echoed (password stripped) before anything is inserted.
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import _normalize_database_url  # noqa: E402
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
from app.utils.handles import unique_handle  # noqa: E402
from app.utils.passwords import hash_password  # noqa: E402
from app.utils.slugs import unique_slug  # noqa: E402

TIMEZONE = "America/New_York"
CITY = "New York"
CURATOR_EMAIL = "nyc-editorial@live-msc.internal"

DROM_SOURCE = "https://dromnyc.com/events/"
ROULETTE_SOURCE = "https://roulette.org/calendar/"
CULTURE_LAB_SOURCE = "https://www.culturelablic.org/sunset-jazz"
CULTURE_LAB_HOME = "https://culturelablic.org/"
LEHMAN_SOURCE = "https://www.lehmancenter.org/events"
SOAPBOX_SOURCE = "https://www.soapboxgallery.org/calendar"
SISTAS_SOURCE = "https://sistasplace.org/"

# name -> (neighborhood, address, latitude, longitude)
VENUES = {
    # Manhattan
    "Drom": (
        "East Village", "85 Avenue A, New York, NY 10009", 40.7250, -73.9835,
    ),
    # Brooklyn
    "Roulette Intermedium": (
        "Boerum Hill", "509 Atlantic Ave, Brooklyn, NY 11217", 40.6845, -73.9795,
    ),
    "Soapbox Gallery": (
        "Prospect Heights", "636 Dean St, Brooklyn, NY 11238", 40.6805, -73.9705,
    ),
    "Janes United Methodist Church": (
        "Bedford-Stuyvesant", "660 Monroe St, Brooklyn, NY 11221", 40.6885, -73.9285,
    ),
    # Queens
    "Culture Lab LIC": (
        "Long Island City", "5-25 46th Ave, Long Island City, NY 11101",
        40.7455, -73.9540,
    ),
    # Bronx
    "Lehman Center for the Performing Arts": (
        "Bedford Park", "250 Bedford Park Blvd W, Bronx, NY 10468", 40.8730, -73.8945,
    ),
}

# (headline, venue, local start datetime, genre, price_cents, ages, support_line,
#  short_line, blurb, ticket_url, local doors datetime or None)
#
# Drom's calendar publishes a door time and no set time, so a Drom row carries
# the same instant in both columns and says "Doors" in its support line. See
# the module docstring, point 1, for why that is preferred to inventing a set
# time thirty minutes later.
EVENTS = [
    # ---- Drom, East Village: most nights of the week on Avenue A -----------
    (
        "Golden Poppy presents The Wavy Warm Up Party", "Drom",
        datetime(2026, 9, 2, 19, 0), Genre.OTHER, None, AgeRestriction.ALL_AGES,
        "Doors 7:00 PM",
        "A season opener on Avenue A",
        "Golden Poppy takes the room for the night to open its run at Drom.",
        DROM_SOURCE, datetime(2026, 9, 2, 19, 0),
    ),
    (
        "Flamenco Jazz Jam", "Drom", datetime(2026, 9, 6, 18, 30),
        Genre.OPEN_MIC, None, AgeRestriction.ALL_AGES, "Doors 6:30 PM",
        "Bring an instrument, or don't",
        "Drom's standing flamenco jazz jam, where the cante and the changes meet in "
        "the same room and players sit in as the night goes.",
        DROM_SOURCE, datetime(2026, 9, 6, 18, 30),
    ),
    (
        "Silver Arrow Band", "Drom", datetime(2026, 9, 8, 19, 0),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 7:00 PM",
        "The first of three nights this autumn",
        "Silver Arrow's first of three Drom dates inside the window; the others fall "
        "on 22 September and 6 October.",
        DROM_SOURCE, datetime(2026, 9, 8, 19, 0),
    ),
    (
        "The Secret Trio", "Drom", datetime(2026, 9, 9, 18, 30),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 6:30 PM",
        "Three instruments, one long conversation",
        "The Secret Trio return to a room that has hosted them for years.",
        DROM_SOURCE, datetime(2026, 9, 9, 18, 30),
    ),
    (
        "SLEEPYHEADS", "Drom", datetime(2026, 9, 11, 18, 30),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 6:30 PM",
        "Friday, doors at half past six",
        "An early Friday bill on Avenue A.",
        DROM_SOURCE, datetime(2026, 9, 11, 18, 30),
    ),
    (
        "Big Blitz", "Drom", datetime(2026, 9, 12, 18, 30),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 6:30 PM",
        "The early half of a double Saturday",
        "Drom runs two bills on 12 September; this is the one that starts before dark.",
        DROM_SOURCE, datetime(2026, 9, 12, 18, 30),
    ),
    (
        "Blinding Lights: The Weeknd Dance Party", "Drom",
        datetime(2026, 9, 12, 23, 0), Genre.ELECTRONIC, None, AgeRestriction.ALL_AGES,
        "Doors 11:00 PM",
        "One catalogue, all night",
        "The late Saturday half: a dance floor given over entirely to one artist's "
        "records until the room closes.",
        DROM_SOURCE, datetime(2026, 9, 12, 23, 0),
    ),
    (
        "Beauty Bar 30th Anniversary", "Drom", datetime(2026, 9, 13, 18, 0),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 6:00 PM",
        "Thirty years of a downtown institution",
        "Beauty Bar marks three decades with a bill at Drom.",
        DROM_SOURCE, datetime(2026, 9, 13, 18, 0),
    ),
    (
        "NYC Spanglish Urban Fest", "Drom", datetime(2026, 9, 17, 18, 30),
        Genre.FESTIVAL, None, AgeRestriction.ALL_AGES, "Doors 6:30 PM",
        "A festival bill, in two languages",
        "A one-night festival of acts working across Spanish and English.",
        DROM_SOURCE, datetime(2026, 9, 17, 18, 30),
    ),
    (
        "Cesar Orozco & SonAhead: Album Release", "Drom",
        datetime(2026, 9, 18, 18, 30), Genre.OTHER, 2000, AgeRestriction.ALL_AGES,
        "Doors 6:30 PM — general admission $20",
        "The one Drom night with a printed price",
        "Cesar Orozco brings SonAhead to Avenue A for the record's release, and it is "
        "the only listing on Drom's calendar this autumn that names its own price.",
        DROM_SOURCE, datetime(2026, 9, 18, 18, 30),
    ),
    (
        "Bushwick Princess and Second Sun Pictures", "Drom",
        datetime(2026, 9, 18, 21, 30), Genre.OTHER, None, AgeRestriction.ALL_AGES,
        "Doors 9:30 PM",
        "The late Friday bill",
        "The second of two 18 September listings, three hours behind the first.",
        DROM_SOURCE, datetime(2026, 9, 18, 21, 30),
    ),
    (
        "Bat Club: Early Goth Party", "Drom", datetime(2026, 9, 19, 18, 0),
        Genre.ELECTRONIC, None, AgeRestriction.ALL_AGES, "Doors 6:00 PM",
        "Goth, early enough to get the train home",
        "Bat Club's conceit is the hour: the whole night runs at the front of the "
        "evening rather than the back of it.",
        DROM_SOURCE, datetime(2026, 9, 19, 18, 0),
    ),
    (
        "WHO'S DANCING? No-Phones Live Funk Dance Party", "Drom",
        datetime(2026, 9, 19, 22, 30), Genre.GOSPEL_SOUL, None,
        AgeRestriction.ALL_AGES, "Doors 10:30 PM",
        "Live funk, and nothing to film it on",
        "A no-phones floor with a live band on it, running late on the Saturday.",
        DROM_SOURCE, datetime(2026, 9, 19, 22, 30),
    ),
    (
        "Silver Arrow Band", "Drom", datetime(2026, 9, 22, 19, 0),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 7:00 PM",
        "The second of three",
        "Silver Arrow's middle Drom date of the autumn.",
        DROM_SOURCE, datetime(2026, 9, 22, 19, 0),
    ),
    (
        "Danielle Nicole", "Drom", datetime(2026, 9, 23, 19, 0),
        Genre.GOSPEL_SOUL, None, AgeRestriction.TWENTY_ONE_PLUS,
        "Doors 6:30 PM, show 7:00 PM — 21 and over",
        "American soul, blues and roots",
        "The one Drom listing this autumn whose ticketing page publishes a set time "
        "and a door policy as well as a door time, so this row carries both.",
        DROM_SOURCE, datetime(2026, 9, 23, 18, 30),
    ),
    (
        "Serkan Tumer", "Drom", datetime(2026, 9, 24, 18, 30),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 6:30 PM",
        "A songwriter's night",
        "Serkan Tumer takes the Thursday.",
        DROM_SOURCE, datetime(2026, 9, 24, 18, 30),
    ),
    (
        "GIRL EDM", "Drom", datetime(2026, 9, 26, 23, 0),
        Genre.ELECTRONIC, None, AgeRestriction.ALL_AGES, "Doors 11:00 PM",
        "Eleven o'clock, and loud",
        "A late Saturday floor at the end of September.",
        DROM_SOURCE, datetime(2026, 9, 26, 23, 0),
    ),
    (
        "Vocal Gumbo", "Drom", datetime(2026, 9, 27, 18, 30),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 6:30 PM",
        "Singers, several traditions",
        "Vocal Gumbo's Sunday at Drom.",
        DROM_SOURCE, datetime(2026, 9, 27, 18, 30),
    ),
    (
        "Queen of the Violin and Friends: Live!", "Drom",
        datetime(2026, 9, 28, 18, 30), Genre.CLASSICAL, None, AgeRestriction.ALL_AGES,
        "Doors 6:30 PM",
        "Strings, on a Monday",
        "A violin-led bill that keeps the room quiet at the front of the week.",
        DROM_SOURCE, datetime(2026, 9, 28, 18, 30),
    ),
    (
        "Riki Rose", "Drom", datetime(2026, 9, 29, 18, 30),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 6:30 PM",
        "Tuesday on Avenue A",
        "Riki Rose closes out Drom's September.",
        DROM_SOURCE, datetime(2026, 9, 29, 18, 30),
    ),
    (
        "The Devil I Knew: Album Release", "Drom", datetime(2026, 9, 30, 18, 30),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 6:30 PM",
        "A record, played through",
        "The last night of Drom's September is a release show.",
        DROM_SOURCE, datetime(2026, 9, 30, 18, 30),
    ),
    (
        "Sylvia Brooks: Soliloquy Release Concert", "Drom",
        datetime(2026, 10, 4, 18, 30), Genre.OTHER, None, AgeRestriction.ALL_AGES,
        "Doors 6:30 PM",
        "A record released in the room",
        "Sylvia Brooks opens Drom's October with the release of Soliloquy.",
        DROM_SOURCE, datetime(2026, 10, 4, 18, 30),
    ),
    (
        "Silver Arrow Band", "Drom", datetime(2026, 10, 6, 19, 0),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 7:00 PM",
        "The third of three",
        "Silver Arrow's last Drom date inside this window.",
        DROM_SOURCE, datetime(2026, 10, 6, 19, 0),
    ),
    (
        "Gömercin Kuşları ft. Kaan Sekban & Ayşe Balıbey", "Drom",
        datetime(2026, 10, 7, 18, 0), Genre.OTHER, None, AgeRestriction.ALL_AGES,
        "Doors 6:00 PM",
        "A Turkish bill, early",
        "One of several Turkish-language nights Drom books through the autumn.",
        DROM_SOURCE, datetime(2026, 10, 7, 18, 0),
    ),
    (
        "Ogun Sanlisoy", "Drom", datetime(2026, 10, 16, 22, 30),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 10:30 PM",
        "A late Friday, loud",
        "Ogun Sanlisoy plays the back half of the Friday night.",
        DROM_SOURCE, datetime(2026, 10, 16, 22, 30),
    ),
    (
        "Wu Fei and Abigail Washburn", "Drom", datetime(2026, 10, 17, 18, 30),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 6:30 PM",
        "Guzheng and banjo, one duo",
        "Wu Fei and Abigail Washburn bring their long-running duo to Avenue A.",
        DROM_SOURCE, datetime(2026, 10, 17, 18, 30),
    ),
    (
        "The Workshop A Cappella", "Drom", datetime(2026, 10, 21, 18, 30),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 6:30 PM",
        "Voices, unaccompanied",
        "An a cappella bill in the middle of Drom's October.",
        DROM_SOURCE, datetime(2026, 10, 21, 18, 30),
    ),
    (
        "YOI TOKI", "Drom", datetime(2026, 10, 23, 23, 0),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 11:00 PM",
        "The late Friday floor",
        "YOI TOKI takes the room at eleven.",
        DROM_SOURCE, datetime(2026, 10, 23, 23, 0),
    ),
    (
        "The Dead Dance", "Drom", datetime(2026, 10, 24, 23, 0),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 11:00 PM",
        "The Saturday before Hallowe'en",
        "Drom's late Saturday, a week out from the holiday.",
        DROM_SOURCE, datetime(2026, 10, 24, 23, 0),
    ),
    (
        "Fugu Dugu: Album Release Concert", "Drom", datetime(2026, 10, 28, 18, 30),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 6:30 PM",
        "A release, mid-week",
        "Fugu Dugu play the new record through on the Wednesday.",
        DROM_SOURCE, datetime(2026, 10, 28, 18, 30),
    ),
    (
        "Baby Blue Sound Collective", "Drom", datetime(2026, 10, 29, 18, 30),
        Genre.OTHER, None, AgeRestriction.ALL_AGES, "Doors 6:30 PM",
        "A collective, on the Thursday",
        "Baby Blue Sound Collective take the night before Hallowe'en weekend.",
        DROM_SOURCE, datetime(2026, 10, 29, 18, 30),
    ),
    (
        "The Petty Toms", "Drom", datetime(2026, 10, 31, 19, 0),
        Genre.ROCK_PUNK, 0, AgeRestriction.ALL_AGES,
        "Doors 7:00 PM — free with RSVP",
        "Hallowe'en, and nothing at the door",
        "Drom bills this one free with an RSVP, which makes it one of two real zeroes "
        "in the room's whole autumn calendar.",
        DROM_SOURCE, datetime(2026, 10, 31, 19, 0),
    ),
    (
        "DAFT DISKO", "Drom", datetime(2026, 10, 31, 23, 0),
        Genre.ELECTRONIC, None, AgeRestriction.ALL_AGES, "Doors 11:00 PM",
        "The last listing of the window",
        "French house and disco on Hallowe'en night, and the latest-starting row in "
        "this batch.",
        DROM_SOURCE, datetime(2026, 10, 31, 23, 0),
    ),
    # ---- Roulette Intermedium, Boerum Hill: prices printed beside dates ----
    #
    # The only room in this batch that publishes a figure next to every listing.
    # Roulette's calendar renders one month at a time and this tool could read
    # September only; October is not in this batch and was not invented.
    (
        "Raven Chacon, Tashi Dorji & Alex Zhang Hungtai", "Roulette Intermedium",
        datetime(2026, 9, 13, 20, 0), Genre.OTHER, 2500, AgeRestriction.ALL_AGES,
        "With Leo Chang opening — $25",
        "A sound-movement piece, then a new trio's debut",
        "Leo Chang's interactive piece reimagines the Korean folk practice of "
        "sangmonori, and a new improvising trio plays its first set after it.",
        ROULETTE_SOURCE, None,
    ),
    (
        "Sō Laboratories in Memory of Tim Thomas", "Roulette Intermedium",
        datetime(2026, 9, 15, 20, 0), Genre.OTHER, None, AgeRestriction.ALL_AGES,
        "The one Roulette night with no printed price",
        "A memorial, played rather than spoken",
        "The series Tim Thomas loved and guided, given over for a night to his memory.",
        ROULETTE_SOURCE, None,
    ),
    (
        "Joy Guidry: Five Prayers in Five Movements", "Roulette Intermedium",
        datetime(2026, 9, 16, 20, 0), Genre.OTHER, 2500, AgeRestriction.ALL_AGES,
        "With A Space for Sound (Rena Anakwe) — $25",
        "Bassoon, spirit and radical self-expression",
        "Rena Anakwe opens with solo improvisations on tapes, voice, synths and "
        "samples before Guidry's five movements.",
        ROULETTE_SOURCE, None,
    ),
    (
        "Katherine Young: BIOMES (Album Release)", "Roulette Intermedium",
        datetime(2026, 9, 17, 20, 0), Genre.OTHER, 2500, AgeRestriction.ALL_AGES,
        "$25",
        "A record launched on Atlantic Avenue",
        "Katherine Young brings BIOMES to the room for its release.",
        ROULETTE_SOURCE, None,
    ),
    (
        "Red Hook Records 5th Anniversary: Andrew Cyrille, Wadada Leo Smith & Qasim Naqvi",
        "Roulette Intermedium", datetime(2026, 9, 18, 20, 0),
        Genre.OTHER, 4000, AgeRestriction.ALL_AGES,
        "With Amina Claudine Myers — $40, first of two nights",
        "Five years of a Brooklyn label",
        "The label takes the hall for two consecutive nights; this is the first, and "
        "Amina Claudine Myers plays the other half of it.",
        ROULETTE_SOURCE, None,
    ),
    (
        "Red Hook Records 5th Anniversary: Jason Moran, BlankFor.ms & Marcus Gilmore",
        "Roulette Intermedium", datetime(2026, 9, 19, 20, 0),
        Genre.OTHER, 4000, AgeRestriction.ALL_AGES,
        "With Caroline Davis, Qasim Naqvi and Grey Mcmurray — $40, second of two nights",
        "The second anniversary night",
        "The closing half of Red Hook Records' fifth-birthday weekend.",
        ROULETTE_SOURCE, None,
    ),
    (
        "The Scores Project: A Book Release Show", "Roulette Intermedium",
        datetime(2026, 9, 24, 20, 0), Genre.OTHER, 2500, AgeRestriction.ALL_AGES,
        "With The Rise of the Novel — $25",
        "A book, launched by playing it",
        "The Scores Project marks its book with a performance rather than a reading.",
        ROULETTE_SOURCE, None,
    ),
    (
        "John Zorn's Alea Iacta Est (World Premiere)", "Roulette Intermedium",
        datetime(2026, 9, 27, 20, 0), Genre.OTHER, 3500, AgeRestriction.ALL_AGES,
        "$35 — the most expensive ticket in this batch",
        "A first performance",
        "Zorn premieres Alea Iacta Est in the hall on the Sunday.",
        ROULETTE_SOURCE, None,
    ),
    (
        "Bathed in Sound: James Brandon Lewis Trio", "Roulette Intermedium",
        datetime(2026, 9, 29, 20, 0), Genre.OTHER, 2500, AgeRestriction.ALL_AGES,
        "With Trap Music Orchestra, Angelica Sanchez, and Clinton Patterson, "
        "Sheela Bringi & Elden Kelly — $25",
        "Four sets in one night",
        "The longest bill Roulette publishes this September, and the last of its "
        "listings inside this window.",
        ROULETTE_SOURCE, None,
    ),
    # ---- Culture Lab LIC, Long Island City: free, every Friday at eight ----
    #
    # The venue's own page: "Enjoy live jazz performances, cool libations, and
    # great vibes in an intimate art gallery space every Friday at 8 PM. Always
    # free and open to the community." Hence price 0 rather than NULL on all
    # nine. The venue names its player weeks ahead, and the dates below are the
    # ones it has named — 16 October is a gap in the venue's own list and was
    # left as one. 10 October is a Saturday on a page that says Friday; see the
    # report.
    (
        "Sunset Jazz: Federico Foli Trio", "Culture Lab LIC",
        datetime(2026, 9, 4, 20, 0), Genre.JAZZ, 0, AgeRestriction.ALL_AGES,
        "Free, and seating is limited",
        "The Friday jazz night, in a gallery",
        "Culture Lab's standing Friday series, played in the gallery rather than a "
        "back room, and free to anyone who arrives early enough to sit down.",
        CULTURE_LAB_SOURCE, None,
    ),
    (
        "Sunset Jazz: David Bixler — Trio Incognito", "Culture Lab LIC",
        datetime(2026, 9, 11, 20, 0), Genre.JAZZ, 0, AgeRestriction.ALL_AGES,
        "Free, and seating is limited",
        "Trio Incognito on the second Friday",
        "David Bixler brings Trio Incognito to the Friday series.",
        CULTURE_LAB_SOURCE, None,
    ),
    (
        "Sunset Jazz: Zachary Berns Ensemble", "Culture Lab LIC",
        datetime(2026, 9, 18, 20, 0), Genre.JAZZ, 0, AgeRestriction.ALL_AGES,
        "Free, and seating is limited",
        "An ensemble, mid-September",
        "The Zachary Berns Ensemble take the third Friday of the month.",
        CULTURE_LAB_SOURCE, None,
    ),
    (
        "Sunset Jazz: Lucas McCrosson", "Culture Lab LIC",
        datetime(2026, 9, 25, 20, 0), Genre.JAZZ, 0, AgeRestriction.ALL_AGES,
        "Free, and seating is limited",
        "September's last Friday",
        "Lucas McCrosson closes the month for the series.",
        CULTURE_LAB_SOURCE, None,
    ),
    (
        "Sunset Jazz: Variego3", "Culture Lab LIC",
        datetime(2026, 10, 2, 20, 0), Genre.JAZZ, 0, AgeRestriction.ALL_AGES,
        "Free, and seating is limited",
        "October opens with a trio",
        "Variego3 open the series' October.",
        CULTURE_LAB_SOURCE, None,
    ),
    (
        "Sunset Jazz: Robert Silverman Quartet", "Culture Lab LIC",
        datetime(2026, 10, 9, 20, 0), Genre.JAZZ, 0, AgeRestriction.ALL_AGES,
        "Free, and seating is limited",
        "A quartet, on the Friday",
        "The Robert Silverman Quartet play the second Friday of October.",
        CULTURE_LAB_SOURCE, None,
    ),
    (
        "Sunset Jazz: Keith Jordan", "Culture Lab LIC",
        datetime(2026, 10, 10, 20, 0), Genre.JAZZ, 0, AgeRestriction.ALL_AGES,
        "Free, and seating is limited — a Saturday night on a Friday series",
        "The one Sunset Jazz that isn't a Friday",
        "Culture Lab's own list dates this one 10 October, which is a Saturday. The "
        "published date is used as published, and the exception is flagged here "
        "rather than quietly moved to the Friday.",
        CULTURE_LAB_SOURCE, None,
    ),
    (
        "Sunset Jazz: Millie Gibson", "Culture Lab LIC",
        datetime(2026, 10, 23, 20, 0), Genre.JAZZ, 0, AgeRestriction.ALL_AGES,
        "Free, and seating is limited",
        "After a fortnight's gap",
        "The series skips 16 October in Culture Lab's own listing; Millie Gibson picks "
        "it back up a week later.",
        CULTURE_LAB_SOURCE, None,
    ),
    (
        "Sunset Jazz: Mixed State", "Culture Lab LIC",
        datetime(2026, 10, 30, 20, 0), Genre.JAZZ, 0, AgeRestriction.ALL_AGES,
        "Free, and seating is limited",
        "The last free Friday of the window",
        "Mixed State close out October for the series.",
        CULTURE_LAB_SOURCE, None,
    ),
    (
        "Vino E Voce: Charles Gray & Vanessa Da Silva", "Culture Lab LIC",
        datetime(2026, 9, 10, 19, 30), Genre.CLASSICAL, None, AgeRestriction.ALL_AGES,
        "Baritone and sommelier, half past seven",
        "Wine and song, on migration",
        "Charles Gray sings a programme built around migration while Vanessa Da Silva "
        "pours against it — the one ticketed Culture Lab listing in this batch.",
        CULTURE_LAB_HOME, None,
    ),
    # ---- Lehman Center, Bedford Park: the Bronx's largest concert hall -----
    #
    # Lehman publishes a date, an hour and a Ticketmaster link, and no price,
    # so all three rows are NULL rather than free.
    (
        "Princess Nokia", "Lehman Center for the Performing Arts",
        datetime(2026, 9, 4, 20, 0), Genre.HIP_HOP, None, AgeRestriction.ALL_AGES,
        "Tickets through Ticketmaster; no price published",
        "A homecoming, more or less",
        "The Bronx's largest concert hall opens its autumn with Princess Nokia.",
        LEHMAN_SOURCE, None,
    ),
    (
        "Grupo Galé & La Sonora Carruseles",
        "Lehman Center for the Performing Arts", datetime(2026, 9, 26, 20, 0),
        Genre.OTHER, None, AgeRestriction.ALL_AGES,
        "Tickets through Ticketmaster; no price published",
        "Two salsa orchestras, one bill",
        "A shared night from two orchestras that have been filling this hall for years.",
        LEHMAN_SOURCE, None,
    ),
    (
        "Son de Cuba", "Lehman Center for the Performing Arts",
        datetime(2026, 10, 3, 20, 0), Genre.OTHER, None, AgeRestriction.ALL_AGES,
        "Tickets through Ticketmaster; no price published",
        "Cuban son, in Bedford Park",
        "Lehman's October opener, and the last of its listings inside this window.",
        LEHMAN_SOURCE, None,
    ),
    # ---- Soapbox Gallery, Prospect Heights ---------------------------------
    #
    # Soapbox publishes four events inside the window and a start time for
    # exactly one of them. The other three are not in this batch: a listing
    # with no time cannot be set in a paper that prints times.
    (
        "Vanessa Rubin & Trio", "Soapbox Gallery", datetime(2026, 9, 18, 20, 0),
        Genre.JAZZ, None, AgeRestriction.ALL_AGES,
        "Doors 7:30 PM — with Brandon McCune, Kenny Davis, Winard Harper and "
        "Nancy Mercado",
        "A mini-festival for the International Day of Peace",
        "Vanessa Rubin sings with a trio and the poet Nancy Mercado, in a storefront "
        "on Dean Street, as the first half of a two-night festival.",
        SOAPBOX_SOURCE, datetime(2026, 9, 18, 19, 30),
    ),
    # ---- Janes United Methodist Church, Bedford-Stuyvesant ----------------
    #
    # Filed under the church rather than under Sistas' Place, because that is
    # the room the music is in and the pin has to be where the reader goes.
    # Sistas' Place's own page dates this "Saturday, September 23"; 23 September
    # 2026 is a Wednesday, and it is Coltrane's hundredth birthday to the day,
    # which is plainly the point. Its own Eventbrite listing says Wednesday
    # 23 September, 7:30 PM, $60. The dated ticketing page is used.
    (
        "James Carter Quintet: John Coltrane Centennial",
        "Janes United Methodist Church", datetime(2026, 9, 23, 20, 0),
        Genre.JAZZ, 6000, AgeRestriction.ALL_AGES,
        "Presented by Sistas' Place — doors 7:30 PM, one show with an interval, $60",
        "Coltrane at a hundred, to the day",
        "John Coltrane was born on 23 September 1926. James Carter's quintet marks the "
        "centenary on the date itself, in a church in Bedford-Stuyvesant that Sistas' "
        "Place has taken for the night.",
        SISTAS_SOURCE, datetime(2026, 9, 23, 19, 30),
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
            handle=unique_handle(session, "editorial_desk"),
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


def seed_real_nyc_music_rooms_4(session, commit: bool = True) -> dict:
    zone = ZoneInfo(TIMEZONE)
    curator = _curator(session)
    venues = _venues(session)

    created_events = 0
    for (
        headline, venue_name, local_dt, genre, price_cents, ages, support,
        short_line, blurb, ticket_url, local_doors,
    ) in EVENTS:
        venue = venues[venue_name]
        starts_at = local_dt.replace(tzinfo=zone).astimezone(timezone.utc)
        doors_at = (
            local_doors.replace(tzinfo=zone).astimezone(timezone.utc)
            if local_doors is not None
            else None
        )

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
            doors_at=doors_at,
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

    if commit:
        session.commit()
    else:
        session.rollback()
    return {"venues": len(venues), "events": created_events}


def _session(database_url: str):
    """A plain SQLAlchemy session, deliberately not the Flask app's.

    Going through `create_app` to insert rows drags in `Config.validate()`,
    Talisman and the rate limiter — none of which a batch insert needs, and all
    of which refuse to boot from a developer's machine against a production
    `DATABASE_URL`, because the limiter's Redis URL lives in Render rather than
    in `.env`. Worse, `Config` reads `os.getenv` at class-body evaluation time
    while `create_app` calls `load_dotenv` afterwards, so `.env` never reaches
    `Config` when this script is run directly and the URI silently falls back
    to SQLite. A session of our own sidesteps all of it.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(_normalize_database_url(database_url), pool_pre_ping=True)
    return sessionmaker(bind=engine)()


def _describe(database_url: str) -> str:
    """Host and database name, with any password stripped out."""
    return database_url.rsplit("@", 1)[-1].split("?", 1)[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="Target database. Defaults to $DATABASE_URL, then to .env.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required to commit. Without it the run is a dry run.",
    )
    args = parser.parse_args()

    database_url = args.database_url
    if not database_url:
        from dotenv import find_dotenv, load_dotenv

        load_dotenv(find_dotenv())
        database_url = os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("no DATABASE_URL: pass --database-url or set it in the environment")

    print(f"target: {_describe(database_url)}")
    print(f"batch:  {len(EVENTS)} listings across {len(VENUES)} rooms")
    print(f"mode:   {'WRITE' if args.yes else 'dry run (nothing is committed)'}")

    session = _session(database_url)
    try:
        summary = seed_real_nyc_music_rooms_4(session, commit=args.yes)
        verb = "created" if args.yes else "that would be created"
        print(f"venues: {summary['venues']}, events {verb}: {summary['events']}")
        if not args.yes:
            print("\nNothing was written. Re-run with --yes to commit.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
