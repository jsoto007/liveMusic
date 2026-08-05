# Live Msc

A listings paper for live music. Bands post a show in three fields; everyone
else reads tonight's bill, marks what they're going to, and finds the room.

Built from the "The Bill" prototype in `design/` on the **Classical** design
system — editorial, book-like, colour applied as stroke rather than fill. See
[CLAUDE.md](CLAUDE.md) for the design rules and the engineering standards this
repo holds itself to.

```
apps/server      Flask 3 + SQLAlchemy 2 + Alembic, Postgres          (the API)
apps/web         React 18 + Vite + TypeScript                        (the SPA)
apps/mobile      Expo / React Native + TypeScript                    (iOS/Android)
packages/shared  Types + ApiClient + the R2 upload helper            (web + mobile)
design/          The source prototype and the Classical stylesheet
```

## Getting set up

Requires Node 20+, pnpm 9, Python 3.11+, and Postgres 14+.

```bash
pnpm install
```

```bash
cd apps/server && python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"
```

Copy the environment template and fill it in — it is key names only, no values:

```bash
cp .env.example .env
```

Create the database and load a readable week of demo listings:

```bash
createdb live_msc && cd apps/server && .venv/bin/python -m flask --app app db upgrade && .venv/bin/python -m flask --app app seed demo
```

## Running it

The API, on port 5001:

```bash
cd apps/server && FLASK_ENV=development .venv/bin/python -m flask --app app run --port 5001
```

The web app, on port 5173 (Vite proxies `/api` to the server, so the browser
talks to one origin and the refresh cookie stays first-party):

```bash
pnpm --filter @live-msc/web dev
```

The mobile app:

```bash
pnpm --filter @live-msc/mobile dev
```

## Tests

```bash
pnpm test
```

That runs the TypeScript suites (the API client's refresh/upload logic, and the
design-token parity check) plus the server's pytest suite. To run the server
tests against real Postgres rather than SQLite — which is the only way the
enum, `TIMESTAMPTZ` and native-UUID behaviour is actually exercised:

```bash
cd apps/server && TEST_DATABASE_URL="postgresql+psycopg2:///live_msc_test" .venv/bin/python -m pytest -q
```

## Email

Address confirmation, password reset, "a band you follow posted a show", and a
reminder the day before a show you said you were going to. The last two are
opt-out per reader and carry an RFC 8058 one-click unsubscribe; the first two
are transactional and cannot be switched off.

Two transports, picked by configuration: **Resend** (an HTTPS API — easier on
Render, which restricts outbound SMTP on some plans) or **SMTP**. With neither
configured the app logs what it would have sent and carries on, so local
development needs no mail credentials at all.

Templates live in `apps/server/app/templates/emails/`. They are table-based
with inline styles — the one place in this repo where writing literal values
instead of design tokens is correct, because Outlook renders HTML with Word
and ignores `<style>`, flex, grid and CSS variables. To see one:

```bash
cd apps/server && flask --app app notify preview show_reminder --out /tmp/preview.html
```

Reminders go out from a scheduled job:

```bash
cd apps/server && flask --app app notify reminders
```

It is safe to run more often than needed — delivery is idempotent per
(reader, show), and its lookup window is wider than its interval so a missed
run recovers on the next one.

## Address autocomplete

Venue and city fields suggest real addresses via **LocationIQ**, proxied
through `/api/v1/geocode/*` so the API key never reaches a browser or a phone.
Picking a suggestion attaches coordinates to the venue, which is what puts the
show on the map.

Results are cached in-process — the free tier is 5,000 lookups a day at
2/second, and an autocomplete field fires on nearly every keystroke. Without a
key the fields degrade to plain text inputs: posting a show still works, the
venue just gets no pin.

## How media works

Audio samples and posters go straight to Cloudflare R2 — **the API never
touches file bytes.** The server issues a presigned POST scoped to one object
key, one content type and one size cap; the client uploads directly; the server
then verifies the object with a `HEAD` before writing any durable row.

Presigned POST rather than PUT is deliberate: only POST carries a
`content-length-range` condition, so R2 itself rejects an oversized upload. See
[CLAUDE.md §4](CLAUDE.md) for the full flow and the threat model it is written
against.

R2 credentials live only in the server's environment. Set `R2_*` in `.env`;
until they are set, upload endpoints return `STORAGE_UNAVAILABLE` (503) and the
rest of the app runs normally.

## Deploying to Render

**Step-by-step: [docs/DEPLOY.md](docs/DEPLOY.md).**

[`render.yaml`](render.yaml) is a Blueprint covering everything: Postgres, a
key-value store for the rate limiter, the API, the static web bundle, and two
cron jobs (reminders, and the storage sweeper). Point Render at the repo, then
fill in the values marked `sync: false` in the dashboard — every one is listed
in [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md).

The static site rewrites `/api/*` to the API service, which keeps the browser
talking to **one origin**. That matters: the refresh token is an httpOnly
`SameSite=Lax` cookie, and a cross-site setup would have the browser drop it —
signing everyone out on every reload.

Migrations run in `preDeployCommand`, so a new instance never takes traffic
against a schema it does not have.

Before a production boot, `Config.validate()` refuses to start on: a missing or
too-short `JWT_SECRET`, a `JWT_SECRET` equal to `SECRET_KEY`, a SQLite
`DATABASE_URL`, an in-memory rate-limit store, or `TESTING` set outside
development. Those are failures you want at boot, not in production traffic.
# liveMusic
