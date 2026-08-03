# Adversarial review — email and geocoding

**Date:** 2026-08-03
**Scope:** the surface added after the initial build — email (verification,
password reset, preferences, unsubscribe, notifications) and the LocationIQ
geocoding proxy.
**Method:** two independent hostile passes, each asked to break its surface and
prove it, not to confirm it works.

**Result:** 11 real defects, all fixed and covered by regression tests. Two of
them would have leaked or destroyed something in ordinary operation, with no
attacker required.

---

## Email

### E1 — Account enumeration by timing · HIGH
`routes/email.py`

`forgot-password` and `resend-verification` returned identical bodies and
statuses — but only did work when the account existed: mint a token, two
commits, two template renders, and a **synchronous** SMTP handshake. Measured
with a realistic transport: **132ms for a hit, 0.5ms for a miss**. A membership
oracle readable in one request, no statistics needed. `resend` leaked a third
state too (verified vs unverified vs absent).

**Fix:** both endpoints pad to a fixed wall-clock floor, so a hit and a miss
take the same time. `login` already did the equivalent by burning a dummy
bcrypt; these pad because the work being hidden is I/O rather than CPU.

### E2 — A mail scanner silently unsubscribed readers · MEDIUM
`routes/email.py`

Unsubscribe mutated state on `GET` — and Flask routes `HEAD` alongside it, so a
bare `HEAD` did it too. That URL is in the `List-Unsubscribe` header *and* the
footer of every optional email. Defender Safe Links, Proofpoint, Barracuda,
Gmail's scanner and iOS Mail's link preview all fetch URLs found in message
bodies. No attacker needed: the recipient's own mail security unsubscribed
them from everything, with no click and no signal.

**Fix:** `GET` renders a one-button confirmation; only `POST` changes anything.
That is what RFC 8058 requires and why.

### E3 — Unauthenticated 500 from a non-ASCII signature · LOW-MED
`utils/email_tokens.py`

`hmac.compare_digest` refuses `str` arguments containing non-ASCII.
`?sig=é` raised `TypeError` → 500 with a traceback, unauthenticated, one
request. It also made a malformed signature distinguishable from a wrong one,
defeating the deliberately-vague response.

**Fix:** compare bytes.

### E4 — The API would mail-bomb an arbitrary address · MEDIUM
`routes/auth.py`, `routes/email.py`

Every limit was keyed by source IP. Register with the victim's address (10/hr),
then resend verification (5/hr), then forgot-password (5/hr) — nothing counted
sends *per recipient*. A rotating-IP source had unbounded volume at one inbox,
from our authenticated sending domain: an inbox flood plus reputational damage
to us. Secondary: each forgot-password retires the victim's previous reset
token, so spamming it kept a legitimate reset from ever completing.

**Fix:** a per-address hourly budget checked inside `deliver`, independent of
who asked. Per-process, so a multi-worker deploy multiplies it — documented,
and the shared-Redis upgrade is noted in the code.

### E5 — A mail-layer failure could 500 the request that triggered it · MEDIUM
`services/email_service.py`, `services/notifications.py`

The contract is stated three times ("never raises"), but the delivery-ledger
write and the token mint both sat *outside* the guard. A transient database
error there — a reset connection, a statement timeout, a deadlock — threw
straight through into a registration whose **user row had already committed**.
The client was told registration failed, retried, and got `EMAIL_IN_USE`
forever.

**Fix:** everything is inside the guard, in both modules. The contract is now
enforced at the boundary rather than holding by accident.

### E6 — A newline in a headline silently killed a notification forever · LOW
`routes/validators.py`

`parse_string` strips only the ends, so an interior `\n` survived into an email
Subject, where Python's header policy refuses it. That raised, was swallowed as
a transport failure, released the delivery claim — and the scheduler then
retried and failed identically, forever. Via an artist name it killed the
announcement to *every* follower of that band.

**Fix:** control characters are stripped in `parse_string`, and subjects are
collapsed at composition. (This is also why header injection was never
exploitable — the failure was availability, not injection.)

### E7 — A rescheduled show lost its reminder · LOW
`services/notifications.py`

The idempotency key was `(user, kind, event_id)`. A band reschedules; the
delivery row from the first date suppresses the reminder for the date that
actually happens. Attendees get a reminder for a night the show isn't on, and
none for the night it is.

**Fix:** the key is a UUID5 over the event id **and** its start instant, so a
reschedule earns a new reminder.

---

## Geocoding

### G1 — The LocationIQ key was written to the log in plaintext · HIGH
`services/geocoding.py`

`requests` embeds the fully-rendered URL — query string, and therefore the API
key — in every connection-level exception: DNS failure, TLS error, connection
refused, too many redirects. The handler interpolated the exception:

```
LocationIQ request failed: HTTPSConnectionPool(...): Max retries exceeded with
url: /v1/autocomplete?q=…&key=SUPER_SECRET_KEY&format=json
```

Straight to stdout, which on any platform means the log aggregator — whose
readership is far wider than the secret store's. It fires on exactly the outage
this module exists to survive, and it breaks the promise `logging_config.py`
makes in its own docstring.

**Fix:** log the exception *type* and the path. Nothing else.

### G2 — One account could burn the entire daily quota · HIGH
`routes/geocode.py`, `services/geocoding.py`

The per-user limit was correctly enforced — just set above the resource it
protected: 300 autocomplete + 120 reverse per hour = **10,080 upstream calls a
day against a 5,000/day quota**. Registration allows 10 accounts/hour from one
IP, so a single IP could drain the quota in under two hours.

The cache did not help, because the key was `strip().lower()`. Seven cosmetic
variants of one address — double space, trailing comma, non-breaking space,
fullwidth character — were seven upstream calls. The `countries` filter was
worse: un-normalised, so `us`, `US`, `us,us`, `ca,us` each bought their own.

**Fix:** the cache key is NFKC-normalised, casefolded, whitespace-collapsed and
stripped of trailing punctuation; country filters are sorted, de-duplicated and
bounded to five valid two-letter codes. A per-process **daily budget** now caps
upstream spend outright, and upstream failures are cached briefly so an outage
is not re-hammered on every keystroke while each request pays the full timeout.

### G3 — Upstream coordinates were unvalidated · MEDIUM
`services/geocoding.py`

No NaN check and no range check, in direct contrast to what `validators.py`
does for *client* input. An upstream `"lat": "nan"` produced a 200 whose body
was literally `{"latitude": NaN}` — **not valid JSON**, so every client's parse
throws and the response that was meant to fail soft takes the form down
instead. Worse, `_resolve_venue` copies those onto the venue row, permanently
poisoning every listing that serializes it.

**Fix:** NaN and out-of-range results are dropped in `_to_place`.

### G4 — Unbounded upstream strings 500'd a show post · MEDIUM
`services/geocoding.py`, `routes/events.py`

A 5,000-character `neighbourhood` was written into a `String(120)` column.
SQLite (the test backend) accepts it silently; Postgres raises
`StringDataRightTruncation` — a `DataError`, not a `requests` exception, so it
escaped the module's "nothing raises" contract entirely and the band's show was
not posted. Exactly the failure
`test_posting_a_show_still_works_when_geocoding_is_down` exists to prevent, via
a different door.

**Fix:** every upstream string is clamped to its column width and non-strings
are dropped, before anything reaches the ORM.

---

## Confirmed already handled

Stated so nobody re-audits them.

**Email:** host-header link injection (links come from configuration, and
`X-Forwarded-Host` cannot reach them); HTML/template injection into emails
(autoescaping on, no `|safe`, `~` concatenation does not bypass it); CRLF into
`To` (the address validator rejects all whitespace); double redemption and
cross-purpose token reuse; a burned token on a rejected weak password; a
preference suppressing transactional mail; unsubscribe signature forgery,
cross-user reuse and UUID-canonicalisation tricks; reading or writing another
user's preferences; session survival across a reset; spam relay via follower
notifications; mail to an arbitrary address via any notification path.

**Geocoding:** the key in a response body; parameter injection or overriding
`key`/`format`/`limit` (trusted values are merged last and win); SSRF via the
path, host or scheme; key exfiltration through an upstream redirect; the rate
limit being per-IP rather than per-user; unauthenticated quota spend; reverse
coordinate abuse and cache-key jitter; cross-user cache contamination; memory
exhaustion via the cache; XSS through `display_name` in either client; debounce
defeat.

---

## Verification

```
server   210 passed, 1 skipped   (SQLite)
server   211 passed              (Postgres)
web       18 passed
mobile     7 passed
lint     ruff + eslint clean across the workspace
```

24 regression tests were added. Each names the defect it covers.

## Still open

- **Both budgets are per-process.** The email per-recipient cap and the
  LocationIQ daily cap are module-level, so a multi-worker deploy multiplies
  them by the worker count. Set them to your quota divided by workers. The
  exact version uses the Redis the rate limiter already has.
- **The timing floor costs latency.** `forgot-password` and
  `resend-verification` now take at least 0.5s. Moving the send to a background
  worker would let both branches be a single DB lookup and remove the pad.
