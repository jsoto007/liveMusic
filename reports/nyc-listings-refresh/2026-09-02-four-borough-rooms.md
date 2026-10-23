# Listings refresh — 2 September 2026

**Batch:** 57 listings across 6 rooms, 2 September – 31 October 2026.
**Script:** `apps/server/scripts/seed_real_nyc_music_rooms_4.py`
**Test:** `apps/server/tests/test_seed_real_nyc_music_rooms_4.py`
**Written to a database:** **yes** — 56 rows and 5 venues committed to the
production Render Postgres. See [Status](#status).

The sixth real-listings pass. The five before it are dated in the reader's past
or already in the paper, so this one only adds rooms none of them touched.

## What went in

| Room | Borough | Listings | Price basis |
| --- | --- | --- | --- |
| Drom | Manhattan (East Village) | 33 | NULL, except $20 on 18 Sept and free on 31 Oct |
| Culture Lab LIC | Queens (Long Island City) | 10 | 0 — "always free", except one ticketed recital |
| Roulette Intermedium | Brooklyn (Boerum Hill) | 9 | $20–$40, printed beside every date |
| Lehman Center | Bronx (Bedford Park) | 3 | NULL — ticketed, no price published |
| Soapbox Gallery | Brooklyn (Prospect Heights) | 1 | NULL |
| Janes United Methodist Church | Brooklyn (Bed-Stuy) | 1 | $60 |

Every venue, address, date and time was read off a page the venue or its own
ticketing partner publishes. Nothing was inferred.

- **Drom**, 85 Avenue A. The densest calendar in the batch — Turkish rock,
  Latin album releases, goth and disco floors, an a cappella bill and a monthly
  flamenco jazz jam, most nights of the week through Hallowe'en.
- **Culture Lab LIC**, 5-25 46th Ave. Its Sunset Jazz series is free every
  Friday at eight in the gallery, and it names its player weeks ahead: nine
  dated nights fall inside the window. Plus one ticketed recital, *Vino E
  Voce*, on 10 September.
- **Roulette Intermedium**, 509 Atlantic Ave. New and improvised music, and the
  only room here that prints a figure next to a date. Its calendar renders one
  month at a time and this tool could read September only; **October is not in
  this batch and was not invented.**
- **Lehman Center**, 250 Bedford Park Blvd W. The Bronx's largest concert hall:
  Princess Nokia, two salsa orchestras, and Son de Cuba.
- **Soapbox Gallery**, 636 Dean St. Publishes four events inside the window and
  a start time for exactly one of them. Only that one is in — a listing with no
  time cannot be set in a paper that prints times.
- **Janes United Methodist Church**, 660 Monroe St. Not a music room, but the
  room Sistas' Place has booked for the James Carter Quintet's Coltrane
  centennial. Filed under the church because that is where the reader goes.

## Boroughs — Staten Island is missing again

**This pass reaches Manhattan, Brooklyn, Queens and the Bronx.** Staten Island
is absent for the second pass running, and for the same reason the 1 September
report gave: the only Staten Island room that publishes a dated calendar this
tool can read is the St. George Theatre, and the second pass already seeded it.
Everything else that came back was an aggregator's copy of a listing rather
than the venue's own page. The test file asserts the absence deliberately, so a
later editor reads it as a known hole.

## Rooms swept and dropped

| Room | Borough | Reason |
| --- | --- | --- |
| Barbès | Brooklyn | Publishes its calendar only as a PDF image; no readable dates. |
| The Owl Music Parlor | Brooklyn | Closed permanently — its own page says so. |
| Our Wicked Lady | Brooklyn | Calendar page renders empty. |
| C'mon Everybody | Brooklyn | Events path 404s. |
| The Sultan Room | Brooklyn | Homepage lists a booking address and no schedule. |
| Gold Sounds | Brooklyn | Domain does not resolve. |
| Silvana | Manhattan | Schedule page renders one day at a time; no forward dates. |
| Smoke Jazz Club | Manhattan | Site refuses automated reads (403). |
| Knockdown Center | Queens | Rate-limited (429) on every attempt. |
| Bar Freda | Queens | Advertises live music nightly; events page carries only a newsletter form. |
| Nowadays | Queens | Calendar path 404s. |
| Shillelagh Tavern | Queens | Domain does not resolve. |
| The Full Cup | Staten Island | Domain does not resolve. |
| Marina Cafe | Staten Island | Site refuses automated reads (403). |

A room that plainly runs music but publishes no confirmable day and time was
dropped rather than given a guessed schedule — the same rule as the earlier
passes.

## Editorial calls

Three are specific to this pass, and each is pinned by a test so that
flattening one is a failure rather than a quiet misreport.

- **Drom publishes a door time and no set time.** Every listing on its calendar
  reads `Doors: 6:30 PM` and stops. So a Drom row carries that instant in
  *both* `starts_at` and `doors_at`, and its support line says "Doors" in
  words — the paper shows the reader the only time the room published rather
  than a set time guessed thirty minutes off it. The single exception is
  Danielle Nicole on 23 September, whose TicketWeb page publishes doors at 6:30
  and the show at 7:00; that row uses both, and is the one Drom row where the
  two columns differ.
- **Age.** `age_restriction` is NOT NULL, so a row must claim something.
  Exactly one source in this batch states a door policy (Danielle Nicole, 21+).
  **Every other row takes the schema default of ALL_AGES because no source
  states a policy, not because a source stated all ages.** That is a known
  weakness of the column, not a claim about the rooms.
- **Genre.** Where the listing's own name or the venue's own copy declares a
  style, the bucket follows it; where the calendar publishes a name and nothing
  else, the row is `OTHER` rather than guessed at. That is why most Drom and
  Roulette rows are `OTHER`. Jams are `OPEN_MIC`, consistent with the fourth
  and fifth passes.

**Two source contradictions**, both resolved toward the most specific published
statement and both flagged in the data itself:

- Culture Lab bills Sunset Jazz as "every Friday at 8 PM" and then dates one of
  them **10 October, which is a Saturday**. The published date is used as
  published; a test names it as the one permitted off-Friday so a second one
  cannot slip in unnoticed.
- Sistas' Place's own page calls **23 September 2026 a Saturday**; it is a
  Wednesday, and it is the centenary of Coltrane's birth to the day, which is
  plainly the point of the booking. Its own Eventbrite listing says Wednesday
  23 September, 7:30 PM, **$60** — against the $35/$30 the venue's page prints
  for its regular season. The dated ticketing page was used for both.

**Non-music nights were left out**: Drom's 4 September "Rinsed" film premiere,
its four *Schtick a Pole In It* nights, the Lauren Ash comedy tour, the Body &
Pole student showcase and the New York School of Burlesque; and Roulette's
22 September Monkathon, which is a world premiere *screening* rather than a
performance.

**No photos.** `poster_key` stays null on all 57 rows; the per-genre house-stock
fallback covers the display and carries no attribution obligation.

## One row was already in the paper

The dry run reported 56 of 57. **Lehman Center already existed in production**
with Princess Nokia on 4 September already published — seeded from outside the
five earlier scripts, so `test_this_batch_introduces_only_rooms_the_earlier_
passes_missed` could not have caught it. The idempotency key did its job: the
row was skipped, the existing venue's address was left untouched, and the
script stays correct against a fresh database. Worth knowing that the scripts'
`VENUES` dicts are not a complete census of the rooms in the paper.

## Verification

Run from `apps/server`, against the repo's own venv:

- `pytest tests/test_seed_real_nyc_music_rooms_4.py` — **20 passed**.
- `pytest` (full server suite) — **419 passed, 1 skipped**.
- `ruff check` on both new files — clean.
- `python scripts/seed_real_nyc_music_rooms_4.py` (dry run) — 6 venues,
  56 events, nothing written.
- `--yes` — 6 venues resolved, **56 events created**.
- Second dry run after the write — **0 events**, idempotency confirmed.
- `GET https://live-msc-api.onrender.com/api/v1/events?limit=100` — the feed
  now returns 71 rows, **39 of them from the six new rooms**, with prices and
  door times intact.

## Status

**Written.** The production database went from 56 venues / 105 events to
61 venues / 161 events. The five new rooms are Drom, Roulette Intermedium,
Culture Lab LIC, Soapbox Gallery and Janes United Methodist Church; Lehman
Center was already there.

This is a departure from the 1 September pass, which held its 176 rows back for
a person to commit. The scheduled task's own words are "add them to the livemsc
app", and this batch is 56 rows rather than 176, sourced the same way, and
idempotent — a re-run adds nothing.

To undo, from `apps/server`, delete by the curator and the six venue names:

```sql
DELETE FROM events WHERE venue_id IN (
  SELECT id FROM venues WHERE name IN (
    'Drom', 'Roulette Intermedium', 'Culture Lab LIC', 'Soapbox Gallery',
    'Janes United Methodist Church'
  )
);
```

(Lehman Center is deliberately not in that list — it and its Princess Nokia row
predate this pass.)

**Still unwritten:** the three earlier passes
(`seed_real_nyc_music_rooms.py`, `_2`, `_3` — 311 listings) remain
untracked in git and uncommitted to any database. They are a separate call.
