# Adversarial review — initial build

**Date:** 2026-08-03
**Scope:** the whole tree at the end of phase 6 — server, shared package, web, mobile.
**Method:** four independent hostile passes, each with a distinct lens and no
knowledge of the others: authentication/session, authorization/IDOR, the
direct-to-R2 upload path, and correctness/data integrity. Reviewers were asked
to *break* the code and to prove each finding, not to confirm it works.

**Result:** 14 real defects found, all fixed and covered by regression tests.
One reviewer (authorization) could not break its surface at all.

Everything below was empirically reproduced before it was fixed — several
against a scratch Postgres, because the SQLite test backend physically cannot
exhibit the concurrency ones.

---

## Authentication and sessions

### A1 — `?client=native` handed the httpOnly refresh token to JavaScript · CRITICAL
`routes/auth.py`

`_wants_native_tokens()` decided purely on a query parameter. Same-origin
script could append `?client=native` to a refresh call and read a raw 30-day
refresh token out of the response body — so `httpOnly`, the entire stated
defence against XSS, bought nothing. It also emitted no `Set-Cookie`, so the
browser kept the now-revoked cookie and the *next* ordinary refresh tripped
theft detection and signed the user out.

**Fix:** the native path is taken only when no refresh cookie was presented. A
request carrying our cookie is a browser, whatever the URL claims.

### A2 — Account lockout was an existence oracle and a remote DoS · HIGH
`routes/auth.py`

A locked account answered `423 ACCOUNT_LOCKED` where an unknown one answered
`401`, and returned before any bcrypt work — a ~200× timing outlier. Nine wrong
guesses proved whether an address was registered.

**Fix:** the locked case now returns the identical `INVALID_CREDENTIALS`
envelope with the same hash cost paid first. The lock is recorded in the log.
The residual trade-off — a third party can still trip the lock on an address
they know — is documented at the constant; the response being indistinguishable
means an attacker cannot even confirm it worked.

### A3 — Refresh rotation had no atomic claim · HIGH
`utils/tokens.py`

Read → check `revoked_at IS NULL` → write, across three statements. Under READ
COMMITTED two concurrent refreshes both observed the token as live, both minted
a child, and the family revocation never fired — exactly the case the design
exists to catch. An expired token also returned early without revoking, so an
expired replay was never treated as theft either.

**Fix:** a single conditional `UPDATE` claims the token; zero rows affected is
treated as reuse and cuts the family. Expiry now revokes as well.

### A4 — Access tokens survived "sign out everywhere" · HIGH
`auth_helpers.py`, `models.py`

`logout-all` revoked refresh tokens only. An access token already in a thief's
hands kept working for its full lifetime — and this is the control someone
reaches for *because* a device was stolen. Lockout had the same hole.

**Fix:** `users.sessions_invalidated_at`; any token whose `iat` predates it is
refused. Stamped on sign-out-everywhere and on lockout.

### A5 — `TESTING=true` disabled every production guardrail · HIGH
`config.py`

`TESTING` is an env var independent of `FLASK_ENV`. Setting it in a deployed
environment unlocked the development fallbacks *and* short-circuited
`validate()`, booting a production process that signed tokens with a secret
committed to this repo — forgeable by anyone who can read it.

**Fix:** fallbacks gate on `IS_DEVELOPMENT` only, and `validate()` now raises
if `TESTING` is set outside development.

---

## Authorization and IDOR

**Nothing exploitable.** 17 adversarial probes — two attacker accounts, forged
`role: admin` tokens, nested-resource confusion, mass assignment, draft
enumeration across every endpoint — were all correctly refused. Confirmed
handled: ownership is re-derived from the DB on every object-scoped route; the
JWT `role` claim is decorative; missing and forbidden are uniformly 404 so ids
cannot be probed; drafts leak nowhere.

Three notes acted on anyway:

- **`serialize_user` defaulted to including the email.** No live leak — every
  call site passes the caller's own record — but the safe behaviour required
  remembering to opt *out*. Flipped to opt-in.
- **`require_role` was dead code**, reading as coverage that did not exist.
  Removed; admin authority lives in `get_owned_artist`.
- **`PATCH /events` skipped the schedule bounds** `create_event` enforces, so a
  published listing could be moved to 1900. Both now share `_check_schedule_bounds`.

---

## The R2 upload path

### U1 — The sample quota was bypassable by concurrency · HIGH
`routes/uploads.py`

Count → check → insert, with no lock. 30 concurrent requests against a quota of
12 produced 30 samples and 30 objects. Sustainable at roughly 1.2 GB/hour of
billable storage per account, with no byte quota to backstop it.

**Fix:** the decision is serialized under `SELECT ... FOR UPDATE` on the artist
row, at both issue and completion.

### U2 — Presigned URLs outlived their tickets, and orphans were unreachable · MEDIUM
`routes/uploads.py`, `services/upload_sweeper.py`

The signature's lifetime came from a *different* config knob than the ticket's.
Abandon a ticket, then POST to the still-live URL: the object lands in the
bucket attached to a ticket the sweeper filtered away from, permanently
unreclaimable. Raising the shared TTL for playback links — an entirely normal
operational change — would silently have extended every upload signature too.

**Fix:** the signature expires with the ticket; the sweeper selects on a new
`swept_at IS NULL` rather than inferring reclaim from `status`.

### U3 — The sweeper marked tickets swept even when the delete failed · MEDIUM
`services/upload_sweeper.py`

`delete_object` swallows transport errors and returns `False`, and the return
value only fed a counter. One R2 hiccup permanently orphaned the whole batch
(up to 200 × 20 MB) — the exact opposite of what the function's own docstring
claimed.

**Fix:** `swept_at` advances only on a confirmed delete; anything else is left
for the next pass.

### U4 — Concurrent photo/poster completions orphaned an object · LOW-MED
Read-modify-write on `photo_key` without a lock: two completions read the same
previous key, the loser's object was written, overwritten, and deleted by
nobody. A double-tap in the mobile client was enough. **Fixed** with a row lock.

### U5 — One-shot completion was enforced by a unique index, not by logic · LOW
Six concurrent completions of one ticket returned `[201, 500, 500, 500, 500,
500]`. **Fixed** with an atomic status claim; losers get a clean 409.

### U6 — Ticket minting was rate-limited per IP · LOW
Trivially multiplied by an attacker with several egress addresses, and shared
by an office behind one NAT. **Fixed:** keyed on the authenticated user.

### Confirmed already handled
Client-chosen keys and prefix traversal (the policy pins an exact key, no
`starts-with`); cross-user targets at both issue and completion; the size cap
(`content-length-range` plus the HEAD re-check); MIME bypass via parameters or
casing; sequential replay; expired redemption; ownership transfer mid-flight;
stored XSS (no `svg+xml`, no `text/html`, no `octet-stream` in the allowlist,
and the type is a signed condition); and the client never sending our bearer
token or cookies to the R2 origin.

---

## Correctness and data integrity

### C1 — The day filter ran after pagination, hiding whole sections · HIGH
`routes/events.py`

Buckets are chronological, so `LIMIT 50` returned the fifty soonest — all
"tonight" — and the weekend filter then removed every one of them. In a city
with 50+ shows earlier in the window, tapping **This weekend** rendered
"Nothing on the bill" while the weekend's shows sat just past the cut. Both
clients send `?day=` with no limit, so the default applied.

**Fix:** the bounded window is fetched, bucketed, then paginated. The response
gained `total` / `has_more` / `window_truncated` so a paging client can tell
the difference between "end of feed" and "filtered out".

### C2 — "This weekend" meant *next* weekend, and split it · HIGH
`routes/serializers.py`

`delta <= 7 and weekday in (4,5,6)` reached a day too far with no check that it
was the *same* weekend. On a Saturday, "This weekend" held only next weekend's
Friday and Saturday — eight days out — while that weekend's Sunday fell into
"Later on". On a Friday it held two different weekends at once and printed a
listing eight days away above one three days away.

**Fix:** an explicit Fri–Sun window anchored on the current date. `day_label`
also stops using a bare weekday name past six days, where "Saturday" was
ambiguous.

### C3 — A network failure destroyed the native session permanently · HIGH
`packages/shared/src/client.ts`, `apps/mobile/lib/auth.tsx`

`refreshSession` treated every non-ok result as "session gone", including
`{status: 0}` from an offline fetch — and on mobile that deleted the refresh
token from the keychain. **Launching the app once in airplane mode signed the
user out for good.**

**Fix:** only a 401/403 clears the credential. Transport failure is not
expiry.

### C4 — The "Tonight" heading carried yesterday's date · MEDIUM
Listings linger six hours past their start, so after midnight the bucket holds
two local dates and the heading took the oldest. Saturday's bill was headed
Friday. **Fixed** by heading from the first show still to come; events now
carry `already_started`.

### C5 — The bounding box dropped venues across the antimeridian · MEDIUM
A box spanning ±180 came out as `(179.84, 180.14)` and a plain `BETWEEN`
excluded a venue 1.3 miles away. **Fixed** with a wrapping longitude clause.

### C6 — "Nearest first" returned the nearest of the *soonest* · MED-LOW
The 300-row pre-filter was ordered chronologically before distance was
computed, so a venue across the street with a show next week lost its place to
a farther one tonight. **Fixed** by pre-ordering on planar distance.

### C7 — Single-flight released before the rotated token was persisted · MED-LOW
`onSession` was fire-and-forget, so a later refresh could read the *old* token
from the keychain, present it, and trip the server's theft detection — a hard
sign-out for doing nothing wrong. **Fixed:** the persist is awaited, and the
token is held in memory as the source of truth.

### C8 — A rejected body read left the UI spinning forever · LOW
`response.text()` sat outside the try guarding `fetch`, so a connection dropped
mid-body escaped a function documented as never throwing. **Fixed.**

### Confirmed correct
`price_cents = 0` vs `NULL` end to end (including `??` rather than `||` at
every client render); timezone handling generally, including DST transitions
and a venue in a different zone from the server; Postgres enum labels and their
declaration order; migration/model parity (zero differences of any kind);
`useResource`'s stale-response guard and the impossibility of a reload loop.

---

## Verification

```
server   134 passed, 1 skipped   (SQLite)
server   135 passed              (Postgres — where the concurrency bugs live)
web       18 passed
mobile     7 passed
lint     ruff + eslint clean across the workspace
```

21 regression tests were added, in `test_auth_hardening.py`,
`test_uploads_hardening.py`, `test_listings_correctness.py`, and the client
durability block in `client.test.ts`. Each one corresponds to a defect above
and names it — none should be removed without understanding what it was for.

## What is still open

- **Lockout DoS.** A third party who knows an address can keep it locked. The
  trade-off is documented at `MAX_FAILED_LOGINS`; the fix, if abuse is ever
  observed, is to scope the counter to (user, source) rather than lengthen the
  window.
- **The double-submit CSRF token is not bound to the session.** Any
  `cookie == header` pair passes. Not exploitable — the cookie is
  `SameSite=Lax` and the routes are POST-only — but it would become so given a
  cookie-write primitive on a sibling origin.
- **No `nosniff` / `Content-Disposition` on the R2 bucket itself.** No
  execution path was found (the allowlist excludes every type browsers sniff,
  and the type is a signed condition), but both are worth setting as defence in
  depth when the bucket is provisioned.
