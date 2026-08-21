# The social turn: profiles, follows, lists, letters, verdicts, and the classifieds board

**Date:** 2026-08-17
**Branch:** `feat/real-map-and-pictures` (uncommitted at time of writing)
**Scope:** full stack — `apps/server`, `packages/shared`, `apps/web`, `apps/mobile`

---

## 1. What shipped

Live Msc grew from a listings paper into a social one. Every feature below is
built across all three apps (Flask API, React web, Expo mobile), with the
server as the single source of rules.

**Profiles.** Every reader now has a public page at `/u/<handle>`: photograph
(R2 avatar), display name, unique `@handle`, bio, home city, member-since,
follower/following/review counts, their band accounts, their public lists,
their recent reviews. Handles are auto-issued at registration from the display
name (collisions get suffixes; existing accounts were backfilled by the
migration) and can be changed under You; grammar is `[a-z0-9_]{3,30}` with a
reserved-names list.

**Follows and blocks.** Reader-to-reader follows (instant — profiles are
public; privacy lives on lists, not accounts), with follower/following pages
and people search. Blocking severs the follow edges both ways in one
transaction, bars new follows in both directions, bars the blocked from
commenting on the blocker's listings, and makes each side's comments and
reviews invisible to the other. A blocked-readers panel under You lists and
undoes them.

**Lists.** Named event lists ("Jazz to catch", "October"), up to 24 per
reader, 200 shows each, each list public or private. Private lists 404 to
everyone but their owner — indistinguishable from nonexistent. Public lists
are shareable pages with the owner's byline. The old one-tap saved/going marks
are untouched and still drive reminders; named lists sit alongside them.

**Comments ("Letters").** Flat, newest-first comment stream under every
non-draft listing, with likes (one per reader, dedup'd bell), author/editor
deletion, and `@handle` mentions that notify the named reader and print as
links on both clients.

**Reviews ("Verdicts").** 1–5 stars plus optional words, one per reader per
show, open only once the show has started and never on a cancelled one.
Editable and deletable by the author; aggregate average/count on the event
detail and review pages.

**Notifications ("Inbox").** In-app inbox with kinds: new follower, comment on
your listing, comment liked, mention, review of your listing, gig
application, application accepted/declined. Unread count badges the masthead
(web) and the Bill header bell (mobile); rows deep-link to their subject and
mark themselves read; "mark all read" available. Server builds the sentence
(`line`) so both clients print the same paper.

**Reports and the editors' desk.** Any comment, review, or person can be
reported with a reason. Admin-only queue at `/admin/reports` (404 to
everyone else) with dismiss / remove-content resolutions; removing content
keeps the report row as the audit line.

**The classifieds board.** Gigs ("jazz trio wanted, Friday, pays $300") can be
posted by anyone: title, description, city/neighborhood/venue, optional
date+timezone, pay in integer cents (`NULL` = not stated, `0` = free — same
rule as door prices), genre. Bands apply with a message (one application per
band per gig, strictly owner-only — **no admin bypass on applying**); posters
read the pile, accept or decline (each notifies the band's current owner),
close/reopen, delete. `GET /gigs` is the public board with city/genre/text
filters. `available_for_hire` (already on the artist model, already editable
under You) now feeds a public **For hire** directory with city/style search.

**The Following feed.** A personal column merging, over a 30-day window:
shows newly published by followed artists or posted by followed readers,
reviews by followed readers, and additions to their *public* lists. Computed
on read (no fan-out tables), merged and paginated in Python per the CLAUDE.md
§5 rule, with `window_truncated` when a source hit its cap.

## 2. Schema

New revision `c9d2e51a7b43` (on `1e57efd27184`): `users.handle/bio/avatar_key`
(+ backfill, then NOT NULL + unique), `user_follows`, `user_blocks`,
`event_lists`, `event_list_items`, `comments`, `comment_likes`, `reviews`,
`gigs`, `gig_applications`, `notifications`, `content_reports`; new enums
`notification_kind`, `report_reason`, `report_status`, `gig_status`,
`gig_application_status`; `upload_purpose` gains `user_avatar` (`ALTER TYPE …
ADD VALUE`; the downgrade deliberately leaves the label — a type rebuild in
active use is riskier than a stray label nothing writes).

**Verified against real Postgres 16** (production's version): the parity test
(`test_migrations.py`) was run locally against a throwaway Homebrew
`postgresql@16` instance — migration chain from empty → head, then
`compare_metadata` — and passed. The test's enum-drop list was extended to
the new types so it stays re-runnable.

## 3. Design decisions worth remembering

- **Notifications are concrete, not polymorphic.** Real FK columns
  (`event_id`, `comment_id`, `gig_id`), every one `ON DELETE CASCADE`, so an
  inbox can never point at something that is gone. Gig decisions are two
  kinds (`gig_accepted`/`gig_declined`) rather than one "updated" kind: the
  bell is a snapshot, and re-reading current status would rewrite history.
- **`inbox.notify()` is the only writer** and owns the rules: never yourself,
  never across a block, opt-in dedupe per fact (follower and like bells ring
  once ever per actor/subject). Dedupe is read-then-insert by design — a
  duplicate inbox line is an annoyance, not a breached invariant, so it does
  not rate a quota's locking.
- **Reports survive their subject.** Subject FKs are `SET NULL` (not CASCADE)
  with an at-most-one check; creation enforces exactly-one in the route. So
  deleting reported content — by author or by moderation — detaches the
  pointer and keeps the audit row. (First draft had CASCADE + exactly-one,
  which would either violate the check or shred the audit trail; caught in
  review, redesigned before commit.)
- **Caps are decided under row locks** (`SELECT … FOR UPDATE` on the owner
  for list creation, on the list for item adds), same pattern as audio-sample
  quotas — count-then-insert loses to concurrency (CLAUDE.md §3.1).
- **Avatar uploads reuse the poster pipeline** with one addition:
  `user_avatar`'s only legal target is the caller (no admin bypass), and the
  attach is the same locked read-modify-write with displaced-object deletion.
- **Aggregate honesty under blocks.** Blocking hides a voice, not its vote:
  review counts/averages include hidden reviewers, and the comment total for
  the room is the true total. Mutual invisibility applies to reads, not
  arithmetic.
- **Feed rides follows, not copies.** No fan-out tables; three bounded
  window queries merged on read. At this paper's scale that is cheaper than
  maintaining write-time copies, and blocks/unfollows take effect instantly.

## 4. Adversarial review — findings and outcomes

Reviewed as attacker and maintainer across all four packages. Everything
below was either fixed before this report or is an explicitly accepted
behavior with its reasoning.

**Fixed during review:**

1. **Report audit destruction** (server, high): `content_reports` subject FKs
   were CASCADE under an exactly-one check — moderation's own remove-content
   action would have deleted the report row it was resolving (PG) or violated
   the check. → `SET NULL` + at-most-one constraint + route-level
   exactly-one; test `test_removing_reported_content_keeps_the_audit_row`.
2. **ORM cascades silently skipped on SQLite** (server, medium):
   `passive_deletes=True` on `Comment.likes/notifications` and
   `Gig.applications/notifications` assumed DB-level FK enforcement, which
   the SQLite test backend does not do — author/editor deletes would have
   left orphans in every test and hidden real regressions. → removed;
   caught by the new cascade tests before it shipped.
3. **Mention case mismatch** (mobile, low): the server parses mentions
   case-insensitively (`@Ada` notifies `ada`) but the mobile renderer only
   linkified lowercase spans, so the two clients printed different letters.
   → `i` flag + lowercased navigation handle + regression test.

**Verified holding (spot list):**

- Every object-scoped write re-derives ownership: foreign lists, reviews,
  comments, gigs, applications all answer 404, indistinguishable from
  missing ids. Application decisions are scoped to the gig in the URL path
  (`application.gig_id` re-checked), so owning one gig decides nothing on
  another.
- Applying to a gig requires *strict* current ownership of the artist —
  deliberately not `get_owned_artist`, whose admin bypass exists for
  moderation, not for auditioning as someone else's band (tested:
  `test_admins_get_no_application_bypass`).
- Notification reads and mark-read are scoped to the bearer in the query
  itself; forged ids mark nothing (tested).
- Draft listings cannot enter lists, comments, or reviews, and there is no
  path from `published` back to `draft` (statuses only move through
  publish/cancel), so public list pages cannot leak unpublished shows. The
  feed additionally skips drafts belt-and-braces.
- The profile serializer only ever ships the *viewer's* block verdict;
  whether the other party blocked the viewer is never serialized — profile
  reads are not a "who blocked me" oracle.
- People search escapes LIKE metacharacters (`%`/`_`); `q=%%` matches
  nothing (tested).
- All new mutating routes authenticate by bearer token, so CSRF double-submit
  does not apply to them (matches existing surface); rate limits sit on
  follows (120/h), blocks (60/h), comments (30/h), likes (240/h), reviews
  (20/h), lists (20/h create, 120/h adds), reports (20/day), gigs (10/day),
  applications (20/day), searches (60–120/min).
- React/RN render all user text as text; mentions are parsed with a strict
  handle grammar and rendered as first-party links only. No HTML paths.

**Accepted behaviors (documented, not bugs):**

- A 403 `BLOCKED` on follow/comment necessarily reveals a block exists —
  the industry-standard trade; the alternative (silent failure) misleads
  the user into thinking they posted.
- Blocking a person does not auto-unfollow their *band accounts* — you
  follow the band, not the person; unfollow remains one tap.
- `parse_string` flattens control characters (including newlines) in comment
  and review bodies — house behavior, identical to blurbs.
- The applications count label on the mobile gig screen can lag one decide
  until reload (cosmetic).

## 5. Evidence

- `apps/server`: **334 passed, 1 skipped** (the Postgres-only parity test,
  separately run and passing against Postgres 16 as above), `ruff` clean.
  ~115 of those tests are new: every new route covered for happy path,
  unauthenticated, wrong-authenticated-user, malformed body, plus the
  adversarial set (block bypass, forged inbox ids, cap fills, avatar target
  spoofing, admin probing, gig/application scoping, feed privacy).
- `pnpm typecheck` 4/4, `pnpm lint` 3/3, `pnpm test` green across web
  (vitest), mobile (vitest, incl. new mention tests), shared, server.
- **Web walked in a real browser** against the one-origin e2e server:
  register → auto handle → bio/avatar panel → band + for-hire flag → gig
  posted → second account → people search → follow → application with
  message → poster's inbox rings twice → notification click-through →
  accept → applicant status flips — all observed working, in the Classical
  styling (screenshots in session).
- Mobile was verified statically only (typecheck/lint/vitest); it was not
  run on a simulator in this session.

## 6. Follow-ups worth considering

- **Email for social events**: the inbox is in-app only; the existing email
  infrastructure (kinds, preferences, idempotent deliveries) could carry
  "new follower" / "application decided" digests later.
- **Handle changes break old profile links** (documented in the UI copy); a
  handle-history redirect table would preserve them.
- **Feed window**: 30 days / 200-per-source with a truncation flag; heavy
  follow graphs may eventually want cursoring or fan-out.
- **Moderation**: the desk handles content; account-level action (suspension)
  is deliberately out of scope and would need `users.is_active` tooling.
- CLAUDE.md was left untouched — the new code follows its existing
  conventions; a §2 architecture note about the social tables could be added
  if the map there should stay exhaustive.
