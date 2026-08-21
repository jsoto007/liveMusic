# Logo and app icons — 2026-08-13

Installed the Claude-design logo export (`~/Downloads/logo-export`) across both
clients: app icon on mobile (iOS light/dark/tinted, Android adaptive +
monochrome), favicon set on web, and an in-app mark beside the wordmark in
both mastheads.

## What changed

- `apps/mobile/assets/icons/` — the four exported 1024px PNGs, verbatim.
  Gold is exactly `--color-accent` (#b68235); light ground #f3f2f2; dark
  ground #191713.
- `apps/mobile/app.json` — `icon` (light), `android.adaptiveIcon` gains
  `foregroundImage` + `monochromeImage` (themed icons on Android 13+), and
  the local plugin below.
- `apps/mobile/plugins/withIosIconAppearances.js` — **SDK 51's prebuild only
  understands a single icon path**; the `ios.icon.{light,dark,tinted}` object
  is SDK 52+. This config plugin runs in the `finalized` mod phase (ordered
  after the base icon mod by the mod compiler) and appends the dark/tinted
  appearance entries to `AppIcon.appiconset` the same way SDK 52 would.
  Delete it on SDK upgrade and move the variants into `ios.icon`.
- `apps/mobile/ios/…/AppIcon.appiconset` — the gitignored-but-local iOS
  checkout got the three-variant catalog installed directly (it previously
  held prebuild's white-square placeholder, since no icon was configured).
- `apps/mobile/components/LogoMark.tsx`, `apps/web/src/components/LogoMark.tsx`
  — the mark as strokes (`react-native-svg` / inline SVG), geometry traced
  from the export (circle c 223.5, r 213.5; polyline 138,223.5 181,181.5
  223.5,245 266,138 309,223.5; stroke 20). Fit validated at IoU 0.93 against
  the source pixels. Accent comes from the theme on both sides; both are
  hidden from assistive tech (the wordmark text carries the name).
- `apps/web/public/` — `favicon.svg` (vector, gold on transparent — legible
  on light and dark tab strips), `favicon-96.png` (tight crop of the
  transparent mark), `apple-touch-icon.png` (opaque light icon, 180px).
- `apps/web/index.html` — icon links + `theme-color` #f3f2f2.
- `.wordmark` now lays out mark + text with `white-space: nowrap` — at phone
  widths the name used to break "Live" / "Msc"; the kicker column yields
  instead.

## Verified

- Throwaway `expo prebuild --platform all` (real ios/ moved aside, restored
  after): iOS catalog contains all three appearances; Android generates
  `ic_launcher.xml` with `<monochrome>` and `iconBackground` #f3f2f2;
  `package.json` untouched by prebuild.
- `turbo run test`, `typecheck`, `lint` — green (incl. the web↔mobile theme
  lockstep test).
- Web dev server: all three icon URLs 200; masthead screenshotted at desktop
  and 375px; favicon.svg rendered and compared to the export.
- iOS simulator build of the real checkout (RNSVG already in the Pods —
  no pod install needed): the compiled `Assets.car` registers
  `UIAppearanceAny` + `UIAppearanceDark` + `ISAppearanceTintable`
  (`xcrun assetutil --info`); the light icon verified on the home screen, the
  dark icon verified live by switching the home-screen icon appearance to
  Dark (on iOS 26 the "Default" icon mode pins light icons even when the
  system theme is dark — dark icons show in the Dark/Auto icon modes);
  in-app masthead verified against the production API. Simulator restored
  to light + Default afterwards.

## Not verified / notes

- **Android is config-level only** — no `android/` folder exists (CNG) and no
  emulator run was done; the monochrome/adaptive wiring is proven from the
  generated project, not a booted device.
- The tinted variant is installed as exported (white mark on gold) and is
  registered in the compiled catalog, but was not displayed live — that
  would repaint every icon on the shared simulator with a chosen tint; the
  selection mechanism is the same one the dark variant proved out.
- `theme-color` in index.html and the icon PNGs necessarily restate ground
  hexes the tokens also carry — static assets can't read CSS variables.
- Pre-existing, unrelated: `test_asking_for_the_weekend_does_not_return_an_
  empty_page` fails on a clean tree (date-dependent window bug; spawned as a
  separate task).
