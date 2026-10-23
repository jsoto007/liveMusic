/**
 * The Classical design system, transcribed for React Native.
 *
 * React Native has no CSS variables, so these values are copied from
 * `apps/web/src/styles/classical.css`. They must not drift: `theme.test.ts`
 * parses that stylesheet and asserts every token here still matches it. If a
 * token changes, change it there first and let the test tell you what to
 * update here.
 *
 * The same rules apply as on the web (CLAUDE.md §1): colour is stroke, never
 * fill; cards and buttons are bordered and unfilled; numbers set tabular.
 */

export const colors = {
  bg: "#f3f2f2",
  surface: "#eae9e9",
  text: "#201f1d",
  accent: "#b68235",

  neutral100: "#f8f4f4",
  neutral200: "#eae7e7",
  neutral300: "#d7d3d3",
  neutral400: "#bab6b6",
  neutral500: "#9b9797",
  neutral600: "#7d7979",
  neutral700: "#605d5d",
  neutral800: "#444141",
  neutral900: "#2d2b2b",

  accent100: "#fff3e4",
  accent200: "#ffe3bf",
  accent300: "#facb8d",
  accent400: "#e1ad66",
  accent500: "#c28d41",
  accent600: "#a06f24",
  accent700: "#7d5411",
  accent800: "#5a3b0a",
  accent900: "#3a270d",
} as const;

/**
 * `color-mix()` has no React Native equivalent, so the alpha-composited
 * variants the stylesheet builds are pre-resolved here as rgba over the
 * ground. The percentages match the CSS exactly.
 */
export const ink = {
  /** `--color-divider`: text at 16% */
  divider: "rgba(32, 31, 29, 0.16)",
  /** Body copy on a listing row. */
  muted: "rgba(32, 31, 29, 0.78)",
  /** Secondary metadata. */
  soft: "rgba(32, 31, 29, 0.60)",
  /** Tertiary — counts, captions, the colophon. */
  faint: "rgba(32, 31, 29, 0.45)",
  /** An inactive tab or a disabled control. */
  ghost: "rgba(32, 31, 29, 0.42)",
  /** Row hover/press wash. */
  wash: "rgba(32, 31, 29, 0.06)",
  /** The accent as a press tint, never as a fill. */
  accentWash: "rgba(182, 130, 53, 0.12)",
} as const;

export const fonts = {
  heading: "CormorantGaramond_600SemiBold",
  /** Display sizes take the normal cut — the bigger it sets, the lighter. */
  headingDisplay: "CormorantGaramond_400Regular",
  body: "Lora_400Regular",
  bodyItalic: "Lora_400Regular_Italic",
} as const;

/** The 1.15× density scale, matching `--space-*`. */
/** The column the paper is set in — the same 940px the web `.page` uses.
 *
 * On a phone this never binds. On an iPad it is the difference between a
 * newspaper column and a line of body copy running the full eleven inches,
 * which is unreadable and is what `supportsTablet: true` gets reviewed on. */
export const maxContentWidth = 940;

export const space = {
  s1: 4.6,
  s2: 9.2,
  s3: 13.8,
  s4: 18.4,
  s6: 27.6,
  s8: 36.8,
} as const;

export const radius = {
  sm: 2,
  md: 4,
  lg: 7,
} as const;

/** Elevation is a whisper here — never a heavy drop shadow. */
export const shadow = {
  sm: {
    shadowColor: colors.neutral900,
    shadowOpacity: 0.14,
    shadowRadius: 2,
    shadowOffset: { width: 0, height: 1 },
    elevation: 1,
  },
  md: {
    shadowColor: colors.neutral900,
    shadowOpacity: 0.16,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 3 },
    elevation: 3,
  },
} as const;

/** The type scale, matching the stylesheet's h1–h6 and body sizes. */
export const type = {
  h1: 42,
  h2: 32,
  h3: 25,
  h4: 20,
  h5: 16,
  h6: 13,
  body: 15,
  small: 13,
  caption: 11,
  kicker: 9.5,
} as const;

/**
 * Figures set tabular so a column of times or prices lines up.
 * `fontVariant` is supported on both platforms for this feature.
 */
export const tabular = { fontVariant: ["tabular-nums" as const] };
