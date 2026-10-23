# What was fixed — 2 September 2026

Companion to [README.md](README.md), which is the audit that found these.
Everything below was run, not assumed: schema changes were applied to a real
Postgres 16 and the parity test run against it; UI changes were walked through
in the simulator and the browser against a local API.

Final state: **451 server tests + 45 client tests pass**, typecheck and lint
clean, iOS Debug *and* Release build under Xcode 26.5, web builds clean.

---

## Still blocking, and not fixable in code

**The R2 token cannot write to the bucket.** Reissue it with Object Read &
Write scoped to the bucket named in `R2_BUCKET`, on Render as well as locally —
and check the name first (`docs/DEPLOY.md` says `live-msc-media`, the running
config says `livemusic`). Walk one upload by hand afterwards: the test suite
mocks R2 and cannot see this.

---

## Server

| Change | Files |
|---|---|
| `POST /api/v1/me/delete` — password-guarded, cascades personal data, cancels upcoming listings, strips the account's own posters, purges storage after the commit | `app/routes/me.py`, `app/services/account.py` |
| Cookie helpers moved out of `routes/auth.py` so logout and deletion cannot drift on cookie paths | `app/utils/auth_cookies.py` |
| `content_reports.event_id` — a listing is reportable; the desk shows it and can take it off the bill | `app/models.py`, `app/routes/reports.py`, `app/routes/serializers.py`, migration `b7c14f2ad903` |
| `head_object` raises `StorageUnavailable` instead of collapsing 403 into "not found"; completion answers 503 and leaves the ticket `PENDING` | `app/services/r2_storage.py`, `app/routes/uploads.py` |
| CSP map-tile origin follows the new basemap | `app/security.py` |
| **SQLite foreign-key enforcement turned on** — every `ON DELETE` in the schema was previously untested | `app/extensions.py` |

New tests: `test_account_deletion.py` (17), `test_reports_events.py` (13),
plus two storage-outage cases in `test_uploads_hardening.py`.

## Mobile

- Delete-account panel, terms and privacy links (`AccountScreen.tsx`, `lib/legal.ts`)
- Report a listing; cancel your own listing (`ShowScreen.tsx`)
- Ticket link field on the post form; **"Buy tickets at <host>"** opening the
  system browser (`PostScreen.tsx`, `ShowScreen.tsx`, `packages/shared/src/tickets.ts`)
- Terms acknowledgement at sign-up; **forgotten-password** link (`AuthScreens.tsx`)
- Apple Maps instead of the watermarked CARTO raster; origin follows the
  reader's home city (`PlanScreen.tsx`)
- Pull-to-refresh on the Bill, Map and List (`components/ui.tsx`, `lib/useResource.ts`)
- No more full-photo-library permission request (3 call sites)
- iPad holds the 940px measure (`components/ui.tsx`, `lib/theme.ts`)

## iOS configuration

- `plugins/withTrimmedInfoPlist.js` removes five boilerplate purpose strings
  (camera, microphone, Face ID, both background-location keys). Registered
  **first** in `plugins`, which is what makes it run last — verified by
  regenerating and reading `ios/LiveMsc/Info.plist`.
- Real purpose strings for location and photos; `ITSAppUsesNonExemptEncryption`.
- `ios.buildNumber`, and `ios.privacyManifests` declaring five collected data
  types **plus** the four required-reason API entries — the override replaces
  the template file wholesale, and omitting them would trip ITMS-91053.
- `eas.json` and `EAS.md`.

## Web

- `/terms` and `/privacy` (`pages/Legal.tsx`), colophon on every page
- Delete-account panel (`pages/Account.tsx`); terms acknowledgement at sign-up
- Report a listing; cancel your own listing (`pages/ShowDetail.tsx`)
- Ticket link field; named buy button (`pages/PostShow.tsx`, `pages/ShowDetail.tsx`)
- Reported listings on the editors' desk (`pages/Desk.tsx`)
- OpenStreetMap tiles, overridable via `VITE_MAP_TILE_URL` (`components/PlanMap.tsx`)

---

## Left open, deliberately

- **Editing a listing.** `PATCH /events/{id}` exists, no client calls it.
  Cancel covers the review requirement; an edit form is a feature.
- **The rate-limiter store is on Render's `free` plan** (`render.yaml:205`).
  Its failure 500s every route but `/health`.
- **Local `.env` `DATABASE_URL` points at production Postgres.** Untouched, but
  a stray `flask db upgrade` would hit the live database.
- **Deleting an account deletes the reports it filed** — `reporter_user_id`
  cascades. Privacy-correct, but an open moderation item disappears with the
  reporter. Changing it to `SET NULL` is a judgement call.
- **`OPERATOR` and the contact address in `pages/Legal.tsx` are placeholders**,
  and both documents want a lawyer's eye.
- Stock-poster repetition; the iOS 26 Liquid Glass back button.
