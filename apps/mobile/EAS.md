# Building and submitting

`eas.json` sits beside `app.json`; every command below runs from `apps/mobile`.

## Before the first build

Two values in `eas.json` are placeholders, because they identify *your* Apple
account and cannot be committed as anything else:

| Field | Where to find it |
|---|---|
| `submit.production.ios.ascAppId` | App Store Connect → your app → App Information → **Apple ID** (a number) |
| `submit.production.ios.appleTeamId` | developer.apple.com → Membership → **Team ID** |

You also need the app record itself to exist in App Store Connect, with bundle
identifier **`org.livemsc.app`** — matching `expo.ios.bundleIdentifier`.

## Versioning

`cli.appVersionSource` is `remote` and the production profile sets
`autoIncrement`, so EAS owns the build number and bumps it on every production
build. Do not hand-edit `ios.buildNumber` in `app.json` — it is the seed value
only, and App Store Connect refuses a build number it has already seen.

`expo.version` (the marketing version, `0.1.0` today) is still yours to set.
Raise it deliberately for a release people will see.

## The commands

```bash
npx eas build --platform ios --profile production
```

```bash
npx eas submit --platform ios --profile production --latest
```

The `preview` profile builds a simulator binary, which is the quick way to
check a change without a device or a signing round-trip:

```bash
npx eas build --platform ios --profile preview
```

## What review will ask for

* **A demo account.** Registration is open and nothing is gated behind email
  verification, so a reviewer can sign up unaided — but give them one anyway,
  with a band account attached, so the posting flow is one tap from their
  first screen.
* **A privacy policy URL** and a **support URL**. The policy is served at
  `/privacy` by the web app; point the listing at that.
* **Location**, because the app declares `NSLocationWhenInUseUsageDescription`.
  The answer is: read once, when the reader taps "use my location" on the map,
  to sort listings by distance. Never in the background, never stored.
