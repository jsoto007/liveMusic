# App Store readiness review — Live Msc iOS

Date: 2026-09-02 · Branch: `feat/real-map-and-pictures` @ `e39475c`
Method: full test suite, fresh typecheck/lint, Debug **and** Release iOS builds
under Xcode 26.5, live walkthrough on iPhone 17 Pro Max + iPad Pro 11" against
the **production** API, plus direct API/R2 probes with curl and boto3.

**Verdict: not ready to submit.** Three blockers, four likely rejections.
Nothing here is speculative — every finding below was reproduced.

---

## What is verified working

| Area | Result |
|---|---|
| Server tests | 399 passed, 1 skipped |
| Client tests | web 21, mobile 17, all passing |
| `pnpm typecheck` / `pnpm lint` (forced, no cache) | clean |
| iOS **Debug** build (Xcode 26.5, RN 0.74.5) | SUCCEEDED |
| iOS **Release** build + Hermes bytecode | SUCCEEDED, app launches and runs |
| Web production build | clean, 448 kB JS |
| Secrets in shipping JS bundle | none found |
| Production API `/health`, listings, search | 200, ~0.3 s |
| Register → post a show → search → detail | works end to end |
| LocationIQ address autocomplete | works |
| iPad | launches and renders, no crash |
| Blocking, comment/review reporting, editors' desk | present |
| Email verification | does **not** gate anything (good — a reviewer can use the app immediately) |

---

## Blockers

### 1. R2 media uploads are dead in production

Every image and audio upload fails. Reproduced three ways:

1. In the app: Account → "Add a portrait" → pick a photo → **"The file could not be uploaded."**
2. Against a presigned PUT minted by the **production** API:
   `PUT … → HTTP 403 <Code>AccessDenied</Code>`
3. With `boto3` against the same bucket: `list_objects_v2` → AccessDenied,
   `put_object` → AccessDenied, `head_bucket` → 403.

The R2 API token cannot access bucket `livemusic` on account `ae5ec7d6…`.
Note `docs/DEPLOY.md` names the bucket `live-msc-media`, while the config uses
`livemusic` — check which is right before assuming the token is at fault.

Impact: posters, band photos, avatars, audio samples — the entire media
subsystem. Readers degrade gracefully (genre stock art fills in), but any band
that tries to upload anything hits a dead end.

**Fix:** repair or reissue the R2 token with Object Read **& Write** scoped to
the bucket named in `R2_BUCKET`, on Render as well as locally.

### 2. No account deletion — guaranteed rejection

App Store Review Guideline **5.1.1(v)**: an app that supports account creation
must support account deletion in-app. There is no `DELETE /me`, no server
route, and no UI. The Account screen ends at "Sign out".

**Fix:** an account-deletion endpoint (with the usual confirmation and a
grace/anonymisation policy for authored listings) plus an entry point on the
Account screen.

### 3. Map tiles ship watermarked "API KEY REQUIRED"

`apps/mobile/screens/PlanScreen.tsx:29` and `apps/web/src/components/PlanMap.tsx:36`
both point at `https://basemaps.cartocdn.com/light_all/…`. CARTO now stamps
**"API KEY REQUIRED — carto.com/basemaps/apikey"** into every unauthenticated
tile. Confirmed by fetching a tile with curl, independently of the app — this is
not a simulator artefact.

Map is a top-level tab, so a reviewer will see it. It is also a CARTO
terms-of-service problem.

**Fix:** get a CARTO API key, or switch to Apple Maps on iOS (drop the
`UrlTile` and let `react-native-maps` use MapKit) with a keyed raster source
for web.

---

## Likely rejections

### 4. A show listing cannot be reported (Guideline 1.2)

`POST /api/v1/reports` accepts exactly one of `comment_id`, `review_id`,
`reported_user_id`. Listings carry a free-text headline, support line, note and
a user-uploaded poster — the app's primary UGC surface — and there is no way to
flag one. `ReportModal` is wired into profiles, reviews and comments only.

### 5. No terms/EULA acceptance, no privacy or terms link anywhere in the app

Guideline 1.2 expects UGC apps to have users agree to terms with a no-tolerance
policy for objectionable content. The Join screen has no such acknowledgement,
and neither client links a privacy policy or terms from anywhere.

### 6. Bands cannot edit, cancel or delete their own listing

The server has `PATCH /events/{id}`, `POST /events/{id}/cancel`,
`POST /events/{id}/publish`, `DELETE /events/{id}`, and serialises
`can_manage` — **no client calls any of them.** Verified by cancelling a test
listing over curl: the server accepted it; there is no in-app path.

Gigs and lists have full manage UI. Events, the core content type, have none.
A typo or a cancelled show is permanent from inside the app.

### 7. Boilerplate and false purpose strings in `Info.plist`

The generated `apps/mobile/ios/LiveMsc/Info.plist` carries:

- `NSMicrophoneUsageDescription` = **"Not used."** — the mic is genuinely never
  used (`expo-av` is playback only); the key should not be there at all.
- `NSCameraUsageDescription` = "Allow $(PRODUCT_NAME) to access your camera" —
  only `launchImageLibraryAsync` is ever called; the camera is never used.
- `NSFaceIDUsageDescription`, `NSLocationAlwaysUsageDescription`,
  `NSLocationAlwaysAndWhenInUseUsageDescription` — all template defaults.
  Always-location in particular draws review scrutiny and is never requested.

These come from the Expo prebuild template, so they **reappear on every EAS
build** unless overridden. `ios/` is gitignored, so editing it locally does
nothing.

**Fix:** set each of these in `app.json` under `ios.infoPlist` — real strings
for what is used, and explicit removal for what is not.

### 8. Full Photo Library access is requested unnecessarily

`AccountScreen.tsx:241`, `PostScreen.tsx:123`, `AccountPanels.tsx:73` all call
`ImagePicker.requestMediaLibraryPermissionsAsync()` before opening the picker.
Without that call, expo-image-picker uses `PHPickerViewController`, which needs
**no permission at all** and shows no prompt. As written the app asks for full
library access to attach one image. Also, the prompt copy says "Choose a poster
or band photo to attach to your listing" while the user is setting a profile
portrait.

---

## Launch readiness / ops

- **No `eas.json`.** Nothing is configured to build or submit. This has to
  exist before anything reaches App Store Connect.
- **Version `0.1.0`, build `1`**, and no `ios.buildNumber` in `app.json` —
  nothing increments the build number between uploads.
- **`NSPrivacyCollectedDataTypes` is empty** in `PrivacyInfo.xcprivacy` while
  the app collects email, display name, user content and coarse location. Keep
  it consistent with the App Store Connect privacy label.
- **The rate-limiter KV store is on Render's `free` plan** (`render.yaml:205`).
  A suspension there takes the whole API to 500 on every route but `/health`.
  That is the single point of failure during App Review — worth upgrading
  before submitting.
- **`head_object` maps 403 AccessDenied to `None`**
  (`apps/server/app/services/r2_storage.py:156-160`), so a credentials outage
  reaches the user as *"We could not find that file in storage. Please upload it
  again."* That is precisely why blocker #1 reads like user error. Surface
  auth/config failures as a distinct 503.

---

## Quality (not rejections, but visible)

- **No forgot-password on mobile.** Web has `/forgot-password`; the iOS sign-in
  screen has no recovery link at all. Email + password is the only auth.
- **No pull-to-refresh or retry** anywhere except Messages. If the first fetch
  fails, the reader gets an error line and no way to try again short of killing
  the app. Apple tests this.
- **Map defaults to Providence, RI** (`PlanScreen.tsx:26`, `41.824, -71.4128`)
  and ignores the signed-in user's `home_city`. Signed in with home city
  New York and all content in NYC, the Map tab still said *"Nothing within five
  miles"* and listed shows 144 miles away.
- **The same genre stock photo repeats 3–4× per screenful** wherever listings
  lack posters — very visible on iPad.
- **iOS 26 renders the nav-bar back button as a white Liquid Glass pill**, which
  fights the Classical system's no-fills rule on every pushed screen.
- **iPad has no max content width** — text lines run the full 11" width. It
  runs and looks fine otherwise, but `supportsTablet: true` means Apple reviews
  it.

---

## Untested

- iOS 15.1 (the declared `deploymentTarget`). Only iOS 26 runtimes are
  installed on this machine.
- Physical device, TestFlight, and the actual archive/upload path (no signing
  configured here). The Release build compiling and running is good evidence,
  not proof.
- iPad Split View / Slide Over (`UIRequiresFullScreen` is `false`).
- Push notifications — not implemented; notices are email-only.

## Test data left behind

- Test account `lvemsc.e2e.2026@example.com` ("Review Tester") exists in
  production. It cannot be removed from the app — see blocker #2.
- The listing it posted, "The Hairline Rules" at Mercury Lounge, was
  **cancelled** via the API (published listings cannot be deleted by design).
