# Browser checks

Two Playwright scripts covering the things a unit test cannot see: whether the
map actually draws, and whether a picture actually gets from a file picker into
storage and back onto the page.

They are **not** wired into `pnpm test`. Running them needs a browser, and a CI
image without one would fail for a reason that has nothing to do with the code.
Run them by hand when touching the map or the upload flow.

```bash
npm i playwright && npx playwright install chromium
pnpm --filter @live-msc/web build          # both run against dist/

node apps/web/e2e/map.mjs                  # self-contained: stubs the API and
                                           # the tile host, serves dist itself

# pictures.mjs drives the real API. Start the throwaway stack first:
python apps/server/devserver.py 5055 &
node apps/web/e2e/pictures.mjs
```

`apps/server/devserver.py` serves the real Flask app and the built SPA from one
origin on SQLite, with R2 replaced by an in-memory bucket reachable over HTTP.
The browser really does POST the file to a presigned-style URL and the server
really does `HEAD` it back before writing the row — only the storage is local.
It also exposes `POST /__control/storage` so a test can simulate a deployment
with no R2 credentials, which is worth exercising because that is a state a
real deploy lands in easily (the `R2_*` values are `sync: false` in
`render.yaml`, so they are empty until someone fills them in).
