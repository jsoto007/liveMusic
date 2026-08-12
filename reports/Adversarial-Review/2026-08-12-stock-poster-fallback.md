# Adversarial review — genre stock-photo fallback for listings

**Change:** every post now prints a photograph. A listing with no uploaded
poster falls back to a house stock image matched to its genre; a poster URL
that dies (presigned GETs expire in minutes) swaps to the same stock via
`onError`. Real posters always win when present. Client-only — no server, DB,
or API change.

## What was read as an attacker

- **Injection via `genre`.** The stock URL is built by indexing a typed
  `Record<Genre, string>` (`STOCK_POSTERS`); a hostile or unknown genre value
  yields `undefined` → `/stock/undefined`, a dead same-origin path — never
  attacker-controlled content in `src`. The map-popup path HTML-escapes the
  URL like every other field (`PlanMap.popupHtml`).
- **Error-swap loop.** `onError` sets `img.src` to the stock path only when the
  current `src` does not already end with it, so a missing stock file cannot
  ping-pong requests. Verified by pointing an event at a nonexistent storage
  key: one 404, one swap, done.
- **CSP.** Stock files are same-origin on both the static web site and the
  devserver, so no `img-src` widening was needed; verified rendering under the
  app's own Talisman headers via `devserver.py`.
- **Licensing/likeness.** The images are downscaled derivatives of the
  original house editorial photographs already checked in under
  `apps/server/seed_photos/nyc/` — no performer likenesses, no third-party
  attribution owed, `poster_credit` stays untouched (and null for stock).
- **Owner nudge unchanged.** `hasImage` on the detail page still keys on the
  real `poster_url`, so an owner still sees "Add a poster" while stock shows.

## What was read as a maintainer

- One source of truth: `STOCK_POSTERS` in `packages/shared`. The record is
  exhaustively typed, so adding a `Genre` without a stock entry fails
  typecheck; `apps/web/src/lib/stock.test.ts` fails if the file is missing,
  overweight (>512 KB), or not actually a JPEG; and
  `apps/mobile/lib/stockPosters.test.ts` fails if the mobile bundle's copy is
  missing from the hand-written Metro asset map or differs byte-for-byte from
  the web's — the same lockstep contract `theme.test.ts` enforces for tokens.
- Accessibility: row plates stay `aria-hidden`; the detail/featured `Plate`
  passes `alt=""` when only stock is shown (it does not carry the act's name,
  so claiming "Poster for X" would be wrong); mobile labels stock as
  "<genre> photograph".
- Mobile image failure state is tracked per-URI so a recycled row or re-used
  plate retries the next event's real poster instead of sticking on stock.

## Proven by running (not assumed)

- `pnpm typecheck`, `pnpm lint`, `pnpm test` — all green
  (web 21, mobile 9, server 219 passed / 1 skipped).
- Live in the browser against `devserver.py` + seeded demo data:
  1. all seven posterless rows + featured plate + detail page print their
     genre's stock;
  2. attaching a real poster to one event makes it beat the stock;
  3. a dead poster URL 404s once and lands on the stock, fully loaded.
- Not run: the Expo app on a device/simulator. The mobile change is
  typechecked and unit-tested but its rendering was not exercised.
