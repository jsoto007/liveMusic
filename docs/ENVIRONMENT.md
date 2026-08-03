# Environment variables

Every variable the server reads, what it does, and whether you have to set it.

`.env.example` is the machine-readable version of this file — key names, no
values. Copy it to `.env` for local work. In production these are set in the
Render dashboard (or come from `render.yaml`).

**Nothing in this list belongs in a client bundle.** The two keys people
usually get wrong — R2 and LocationIQ — are deliberately server-side only:
uploads go through a presigned URL the server mints, and geocoding goes
through a proxy. Neither key is ever sent to a browser or a phone.

---

## Required in production

The server refuses to boot without these. `Config.validate()` checks them
before anything binds, so a misconfiguration fails at deploy time rather than
on a user's first request.

| Variable | What it is |
|---|---|
| `SECRET_KEY` | Flask's signing key. Any long random string. On Render, `generateValue: true` handles it. |
| `JWT_SECRET` | Signs access and refresh tokens. **Must be ≥32 characters and must differ from `SECRET_KEY`** — boot fails otherwise, so that leaking one does not hand over the other. |
| `DATABASE_URL` | Postgres connection string. A `postgres://` URL is rewritten to `postgresql+psycopg2://` automatically. SQLite is rejected in production. |
| `RATELIMIT_STORAGE_URI` | Redis/Valkey URL. **`memory://` is rejected in production**: an in-memory limiter is per-process, so two workers would silently double every published limit. |
| `FLASK_ENV` | Set to `production`. Anything else enables development fallbacks. |

## Origins

| Variable | Default | What it is |
|---|---|---|
| `FRONTEND_URL` | — | The public address of the web app. Drives CORS, the CSP, the HTTPS redirect, and every link in every email. Comma-separated for several. A bare hostname is accepted and gets `https://` prepended. |
| `CORS_ORIGINS` | empty | Extra allowed origins beyond `FRONTEND_URL`. Usually unnecessary. |
| `PUBLIC_API_URL` | falls back to `FRONTEND_URL` | Where links that must hit the API directly point — specifically one-click unsubscribe, which mail providers POST with no browser. Only needed when the API is on a different origin from the SPA. |

> **Why this matters:** links in emails are built from configuration, never
> from the request's `Host` header. Trusting the inbound Host is how a genuine
> password-reset token ends up in a link pointing at an attacker's domain.

---

## Cloudflare R2 — audio and images

Server-side only. The API never handles file bytes: it mints a presigned POST,
the client uploads straight to R2, and the server then verifies the object
with a `HEAD` before writing any row.

| Variable | Required | What it is |
|---|---|---|
| `R2_ACCOUNT_ID` | yes* | Your Cloudflare account id. Used to derive the endpoint if `R2_ENDPOINT_URL` is unset. |
| `R2_ACCESS_KEY_ID` | yes | R2 API token id. |
| `R2_SECRET_ACCESS_KEY` | yes | R2 API token secret. |
| `R2_BUCKET` | yes | Bucket name. One bucket holds everything; keys are namespaced by purpose. |
| `R2_ENDPOINT_URL` | no | Overrides the derived `https://<account>.r2.cloudflarestorage.com`. |
| `R2_REGION` | `auto` | Leave as `auto` for R2. |
| `R2_PUBLIC_BASE_URL` | no | A public CDN base for the bucket. **Leave unset** to serve every object through short-lived presigned GETs, which is the safer default. Set it only if you deliberately make the bucket public and want cacheable media. |
| `R2_SIGNED_URL_TTL_SECONDS` | `900` | Lifetime of a playback (GET) signature. |
| `UPLOAD_TICKET_TTL_SECONDS` | `900` | Lifetime of an upload ticket **and** its POST signature — they expire together on purpose. |
| `AUDIO_MAX_BYTES` | `20971520` (20 MB) | Per-sample cap. Enforced by R2 itself via a `content-length-range` policy condition, then re-checked on completion. |
| `IMAGE_MAX_BYTES` | `8388608` (8 MB) | Per-image cap for posters and band photos. |
| `AUDIO_SAMPLES_PER_ARTIST` | `12` | How many sound samples one band may hold. |

\* Either `R2_ACCOUNT_ID` or `R2_ENDPOINT_URL` is needed — not both.

**Bucket setup.** Create one R2 bucket and an API token scoped to it with
object read/write. If the browser will upload directly (it will), add a CORS
rule on the bucket allowing `POST` from your `FRONTEND_URL` origin with
`Content-Type` in the allowed headers. Without that the browser blocks the
upload before it leaves the page.

Until these are set, upload endpoints return `503 STORAGE_UNAVAILABLE` and the
rest of the app runs normally.

---

## Email

Set **either** `RESEND_API_KEY` **or** the `SMTP_*` group. Resend wins if both
are present. With neither, the app logs what it would have sent and carries on
— local development needs no mail credentials.

| Variable | Required | What it is |
|---|---|---|
| `MAIL_FROM_ADDRESS` | yes, to send | The From address. Must be on a domain you have verified with your provider, or everything lands in spam. |
| `MAIL_FROM_NAME` | no (`Live Msc`) | Display name on the From header. |
| `RESEND_API_KEY` | one of | Resend API key. Simplest option on Render, which restricts outbound SMTP on some plans. |
| `SMTP_HOST` | one of | SMTP server hostname. |
| `SMTP_PORT` | `587` | `587` uses STARTTLS; `465` uses implicit TLS. Both are encrypted — plaintext is never used. |
| `SMTP_USERNAME` | no | Omit for a relay that authenticates by IP. |
| `SMTP_PASSWORD` | no | |
| `SMTP_TIMEOUT_SECONDS` | `15` | |
| `EMAIL_HTTP_TIMEOUT_SECONDS` | `10` | Timeout for the Resend API call. |
| `EMAIL_PER_RECIPIENT_HOURLY` | `6` | Cap on messages to **one address** per hour, whoever asked. Every route limit is keyed by source IP, so without this a rotating-IP caller had unbounded volume at a single inbox. Per-process — divide by your worker count. |
| `EMAIL_RESPONSE_FLOOR_SECONDS` | `0.5` | Wall-clock floor on "send me a link" responses so a hit and a miss cannot be told apart by timing. Only set to `0` in tests. |

**What gets sent:** address confirmation, password reset, "a band you follow
posted a show", and a reminder the day before a show you said you were going
to. The last two are opt-out per reader and carry a one-click unsubscribe
header; the first two are transactional and cannot be suppressed.

---

## LocationIQ — address autocomplete

Server-side only. Every lookup is proxied so the key cannot be lifted from a
JS bundle or a mobile binary and spent by someone else.

| Variable | Required | What it is |
|---|---|---|
| `LOCATIONIQ_API_KEY` | yes, for autocomplete | Your LocationIQ access token. |
| `LOCATIONIQ_BASE_URL` | `https://us1.locationiq.com/v1` | Change to `https://eu1.locationiq.com/v1` for the EU region. |
| `LOCATIONIQ_TIMEOUT_SECONDS` | `6` | |
| `GEOCODE_CACHE_SECONDS` | `3600` | How long an identical lookup is served from memory. The free tier is 5,000/day at 2/sec and an autocomplete field fires on nearly every keystroke, so this matters. |
| `GEOCODE_CACHE_MAX_ENTRIES` | `2000` | Cache size before eviction. |
| `LOCATIONIQ_DAILY_BUDGET` | `2000` | Hard cap on upstream calls **per process per day**. The free tier is 5,000/day — divide by your worker count. `0` disables the ceiling, which means an unbounded bill. |

Without a key, the address fields degrade to plain text inputs — posting a
show still works, the venue just gets no coordinates and therefore no map pin.

---

## Optional

| Variable | Default | What it is |
|---|---|---|
| `SENTRY_DSN` | empty | Error tracking. Unset disables it entirely. |
| `LOG_LEVEL` | `INFO` | |
| `ACCESS_TOKEN_TTL_SECONDS` | `900` | Access token lifetime. Held in memory by clients only. |
| `REFRESH_TOKEN_TTL_SECONDS` | `2592000` (30 days) | Refresh token lifetime. Rotated on every use. |

---

## The mobile app

The only thing the app needs is where the API lives. It is **not** a secret,
and no other value from this document belongs in a mobile build.

Set `extra.apiUrl` in `apps/mobile/app.json`, or `EXPO_PUBLIC_API_URL` at build
time. A release build refuses to start against a plain `http://` URL.

---

## Minimum to go live

```
FLASK_ENV=production
SECRET_KEY=…                      # generated
JWT_SECRET=…                      # generated, ≥32 chars, ≠ SECRET_KEY
DATABASE_URL=…                    # from the Render Postgres
RATELIMIT_STORAGE_URI=…           # from the Render key-value store
FRONTEND_URL=https://livemsc.org

R2_ACCOUNT_ID=…
R2_ACCESS_KEY_ID=…
R2_SECRET_ACCESS_KEY=…
R2_BUCKET=live-msc-media

MAIL_FROM_ADDRESS=notices@livemsc.org
RESEND_API_KEY=…                  # or the SMTP_* group

LOCATIONIQ_API_KEY=…
```

Everything above that line has a working default or degrades gracefully.
