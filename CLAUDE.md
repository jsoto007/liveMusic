# Project: Live Msc

A listings paper for live music. Bands post shows in three fields; everyone else
reads tonight's bill, marks what they're going to, and finds the room.

Derived from the "The Bill" prototype (`design/` — see §1). The product name is
**Live Msc**; the prototype's masthead wordmark "The Bill" is kept only as the
name of the home *section* ("Tonight's bill"), never as the app name.

---

## 1. Design system — Classical

The whole UI is one design system, "Classical", and it is **not** negotiable per
screen. Source of truth for the tokens:

- Web: `apps/web/src/styles/tokens.css` (the `:root` variable block) and
  `apps/web/src/styles/classical.css` (the component layer).
- Mobile: `apps/mobile/lib/theme.ts` — the SAME numbers, transcribed, because
  React Native has no CSS variables. If you change a token on one side you MUST
  change it on the other; `apps/mobile/lib/theme.test.ts` asserts the two stay
  in lockstep by parsing the CSS.

### Direction

Editorial, book-like, on a soft near-white ground. Justified body copy, tight
leading, hairline rules carrying the structure. **Color is applied as stroke,
never as fill** — buttons are 1px accent outlines on transparent, cards are
bordered and unfilled. Photographs go through the `.plate` wrapper (a warm
archival grade inside a thin surface-colored mat) so they read as tipped-in
book plates, not banners.

### Do

- Justify body copy; let the hairlines do the structural work.
- Draw with borders, rules and underlines. Keep large fills off the page.
- Set numbers tabular (`font-variant-numeric: tabular-nums`) wherever they
  stand as figures or columns — times, prices, counts, tables. Running prose
  keeps its text figures.
- Give text room. The spacing scale is airy (density 1.15×) on purpose.

### Don't

- Do not fill cards or buttons with solid accent color.
- Do not use heavy drop shadows — elevation here is a whisper.
- Do not tighten leading or crowd the margins.
- Do not swap in a sans-serif for emphasis. Weight and italics do that job.
- Do not hard-code a hex, a font name, or a px value the tokens already carry.

### Contrast rule (accessibility, not taste)

The accent (`#b68235`) against the ground is tuned to ~3:1 — enough for icons,
large text and interface chrome, **not** for body copy. For paragraph-size text
in the accent use `--color-accent-700`. Every interactive element needs a
`:focus-visible` ring (`2px solid var(--color-accent)`, offset 2px); never leave
the browser default.

### Icons

Lucide throughout (`lucide-react` on web, `lucide-react-native` on mobile).

---

## 2. Architecture

```
apps/server    Flask 3 + SQLAlchemy 2 + Alembic (Flask-Migrate). Postgres.
apps/web       React 18 + Vite + TypeScript + Tailwind. Same-origin with the API.
apps/mobile    Expo / React Native + TypeScript.
packages/shared TypeScript types + ApiClient shared by web and mobile.
```

The server is the only thing that talks to the database, and the only thing that
holds R2 credentials. Clients never see a secret.

### API conventions

- Every route lives under `/api/v1/`.
- Every response is the envelope `{"data": ..., "error": null}` or
  `{"data": null, "error": {"code", "message", "details"}}`. Build them with
  `app/routes/response.py::ok` / `::error` — never `jsonify` a bare payload.
- `code` is a stable SCREAMING_SNAKE string clients may branch on. `message` is
  human-readable and safe to show a user. Internal detail (SQL, stack, enum
  names) never crosses this boundary.
- Input parsing goes through `app/routes/validators.py`. A malformed body
  returns `VALIDATION_ERROR`, never a 500.
- List endpoints paginate with `limit`/`offset` (`parse_pagination`), max 100.

### Layering

`routes/` parse + authorize + serialize. `services/` hold the domain logic and
are the only place a multi-step write is coordinated. `models.py` holds schema
and invariants. A route that contains business rules is a bug in the making —
push it into a service.

---

## 3. Security standards

These are the defaults. Deviating from one requires a comment explaining why.

1. **Tokens.** Short-lived JWT access token (15 min) held **in memory only** on
   clients — never `localStorage` (an XSS would exfiltrate it), never
   `AsyncStorage`. The refresh token is an httpOnly, Secure, SameSite=Lax cookie
   on web; on mobile it lives in `expo-secure-store`. Refresh tokens are
   rotated on every use and the old one is revoked — reuse of a revoked token
   invalidates the whole family (theft detection). Rotation is claimed with a
   single conditional `UPDATE`, never read-then-write: two concurrent refreshes
   both passing a read-based check is exactly the theft the design is meant to
   catch. Revoking refresh tokens is not enough on its own —
   `users.sessions_invalidated_at` is what actually ends sessions already open,
   and must be stamped by anything that means "sign out" (logout-all, lockout,
   and any future password change).

   Whether a client gets its refresh token in a cookie or in the response body
   is decided by **how the request arrived**, never by a query parameter. A
   request bearing our cookie is a browser whatever it claims, and handing that
   token to JavaScript makes `httpOnly` worthless.

   Any check that gates a limited resource — a quota, a one-shot ticket, a
   lock — must be atomic. Count-then-check-then-insert is not: under READ
   COMMITTED every concurrent caller reads the same pre-attack count and every
   one of them passes. Use `SELECT ... FOR UPDATE` on the owning row, or a
   conditional `UPDATE` whose affected-row count is the decision.
2. **CSRF.** Any cookie-authenticated state-changing request requires the
   double-submit `X-CSRF-Token` header matching the `csrf_token` cookie.
3. **Passwords.** bcrypt, cost ≥ 12. Minimum 12 characters, checked against a
   common-password list. Login is rate-limited and answers identically for
   "no such user" and "wrong password" (no account enumeration).
4. **Authorization.** Every object-scoped route re-derives ownership from the
   authenticated user — never from a client-supplied id. `require_artist_owner`
   is the guard for anything touching an artist's shows, samples or profile.
   Assume every id in a URL is attacker-chosen.
5. **Rate limits.** Global default plus tighter per-route limits on auth,
   search, and upload issuance. `/health` is exempt (the platform polls it).
6. **Headers.** Talisman with a strict CSP (no `unsafe-inline`, no
   `unsafe-eval`), HSTS, and `force_https` everywhere but loopback.
7. **Secrets.** Only ever read from environment. `.env` is git-ignored;
   `.env.example` carries the key names and no values. If a credential ever
   lands in a commit, rotate it — do not just delete the line. A development
   fallback gates on `IS_DEVELOPMENT` and nothing else: `TESTING` is an
   independent env var, and letting it unlock fallbacks (or skip
   `Config.validate()`) means one stray variable boots production with a secret
   that is a literal in this repo.
8. **Logging.** Structured JSON with a request id. Never log a token, password,
   presigned URL, or full email address.

---

## 4. Media and R2 — direct upload, always

Audio samples and posters go to Cloudflare R2. **The server never proxies file
bytes.** The flow is:

1. `POST /api/v1/uploads` with `{purpose, filename, content_type, size_bytes}`.
   The server authorizes the purpose against the caller, checks the MIME
   allowlist, the size cap and the per-artist quota, mints an opaque object key
   (the client never chooses the key), records a `media_uploads` row as
   `PENDING`, and returns a **presigned POST** — url + fields.
2. The client posts the file straight to R2 with those exact fields.
3. `POST /api/v1/uploads/{id}/complete`. The server issues a `HEAD` against the
   object and verifies it exists, its size is within the cap, and its
   content-type matches what was signed. Only then does the durable row
   (`audio_samples`, or the poster key on an event) get written and the upload
   marked `COMPLETED`.

Why presigned **POST** and not PUT: a presigned POST carries a
`content-length-range` condition, so R2 itself rejects an oversized upload. A
presigned PUT cannot enforce size — the client could sign a 10 MB intent and
push 10 GB. Both are in `services/r2_storage.py`; use `generate_presigned_post`
for uploads.

Playback URLs are short-lived presigned GETs (`R2_SIGNED_URL_TTL_SECONDS`,
default 900). They are minted per-request at serialization time and must never
be cached in the database.

Unfinished `PENDING` uploads and their orphaned objects are swept by
`sweep_abandoned_uploads` — an upload that is never completed costs storage.

---

## 5. Database conventions

- **Postgres enums are declared with `values_callable`**, so the stored label is
  the lowercase `.value` (`"published"`), not the Python member name
  (`"PUBLISHED"`). This is deliberate and differs from some of the other
  projects in this account — it means raw SQL in a migration uses the same
  literal the ORM does, and there is no uppercase/lowercase trap. See
  `app/models.py::pg_enum`. Always go through that helper.
- **Never amend a migration that has been applied anywhere.** Once a revision
  has run against a real database its file is frozen; a schema change goes in a
  NEW revision. An amended applied revision is a silent no-op on every existing
  database while a from-scratch CI run still passes, so code and prod schema
  diverge and the next deploy 500s.
- Money is integer **cents**, never a float. A free show is `price_cents = 0`;
  "unknown/varies" is `NULL` — they are different and render differently.
- All timestamps are `TIMESTAMP WITH TIME ZONE`, stored UTC, produced by
  `datetime.now(timezone.utc)`. Never `utcnow()` (it returns a naive datetime
  and silently compares wrong against aware columns).
- An event's local wall-clock time matters to a reader ("9:00 PM"), so events
  carry both `starts_at` (UTC instant) and the venue's IANA `timezone`. Format
  in the venue's zone, never the server's.
- **A filter the database cannot express must not be applied after
  pagination.** The day buckets are decided in the venue's local calendar, so
  they are computed in Python — which means `LIMIT` in SQL would page over the
  *unfiltered* set and the filter would then empty the page. Fetch the bounded
  window, filter, then slice; and return `total`/`has_more` so a client can
  tell "end of feed" from "filtered out".

---

## 6. Testing standard

- `pytest` for the server, against SQLite in-memory for unit/route tests and
  Postgres in CI for migration tests. `apps/server/tests/conftest.py` builds an
  app with `TESTING=True` and a fresh schema per test.
- A route is not done until it has tests for: the happy path, the unauthorized
  caller, the *wrong* authenticated caller (IDOR), and a malformed body.
- Anything touching uploads, auth, or authorization gets an adversarial test —
  one written to break it, not to confirm it works.
- **No assumptions — prove behavior with a real test run.** Do not report a
  phase complete on a change you have not executed. If something could not be
  run (a device build, a live R2 call), say so explicitly rather than implying
  it passed.

Run everything from the repo root:

```bash
pnpm test
```

---

## 7. Working agreements

- Build in phases; each phase leaves the tree green (typecheck, lint, tests)
  before the next one starts.
- Every phase ends with an independent adversarial review pass over what
  changed — read it as an attacker and as a maintainer, not as the author.
- Reports go in `reports/`, in a subfolder named for the topic.
- Before opening or updating a PR, rebase onto the latest main and resolve
  conflicts as part of finishing the work — not after review finds them.
