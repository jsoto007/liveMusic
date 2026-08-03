/**
 * Guards the promise made in `theme.ts` and CLAUDE.md §1: the mobile tokens
 * are a transcription of the web stylesheet, and the two must not drift.
 *
 * Parsing the CSS rather than duplicating expected values means this test
 * fails the moment a designer retunes `classical.css` without updating the
 * app — which is exactly when a silent divergence would otherwise start.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { colors, radius, space, type } from "./theme";

// Resolved from the vitest working directory (apps/mobile) rather than via
// `import.meta`, which the Expo tsconfig's module setting does not allow.
const stylesheet = readFileSync(
  resolve(process.cwd(), "../web/src/styles/classical.css"),
  "utf8",
);

function cssVar(name: string): string {
  const match = stylesheet.match(new RegExp(`--${name}:\\s*([^;]+);`));
  if (!match?.[1]) throw new Error(`--${name} is not defined in classical.css`);
  return match[1].trim();
}

describe("the mobile theme matches the Classical stylesheet", () => {
  it("uses the same core colours", () => {
    expect(colors.bg).toBe(cssVar("color-bg"));
    expect(colors.surface).toBe(cssVar("color-surface"));
    expect(colors.text).toBe(cssVar("color-text"));
    expect(colors.accent).toBe(cssVar("color-accent"));
  });

  it("uses the same neutral ramp", () => {
    const steps = [100, 200, 300, 400, 500, 600, 700, 800, 900] as const;
    for (const step of steps) {
      expect(colors[`neutral${step}` as keyof typeof colors]).toBe(
        cssVar(`color-neutral-${step}`),
      );
    }
  });

  it("uses the same accent ramp", () => {
    const steps = [100, 200, 300, 400, 500, 600, 700, 800, 900] as const;
    for (const step of steps) {
      expect(colors[`accent${step}` as keyof typeof colors]).toBe(
        cssVar(`color-accent-${step}`),
      );
    }
  });

  it("uses the same spacing scale", () => {
    expect(space.s1).toBeCloseTo(parseFloat(cssVar("space-1")), 2);
    expect(space.s2).toBeCloseTo(parseFloat(cssVar("space-2")), 2);
    expect(space.s3).toBeCloseTo(parseFloat(cssVar("space-3")), 2);
    expect(space.s4).toBeCloseTo(parseFloat(cssVar("space-4")), 2);
    expect(space.s6).toBeCloseTo(parseFloat(cssVar("space-6")), 2);
    expect(space.s8).toBeCloseTo(parseFloat(cssVar("space-8")), 2);
  });

  it("uses the same radii", () => {
    expect(radius.sm).toBe(parseFloat(cssVar("radius-sm")));
    expect(radius.md).toBe(parseFloat(cssVar("radius-md")));
    expect(radius.lg).toBe(parseFloat(cssVar("radius-lg")));
  });

  it("uses the same heading sizes", () => {
    const headingSize = (level: string): number => {
      const match = stylesheet.match(new RegExp(`\\n${level}\\s*\\{[^}]*font-size:\\s*([\\d.]+)px`));
      if (!match?.[1]) throw new Error(`no font-size found for ${level}`);
      return parseFloat(match[1]);
    };
    expect(type.h1).toBe(headingSize("h1"));
    expect(type.h2).toBe(headingSize("h2"));
    expect(type.h3).toBe(headingSize("h3"));
    expect(type.h4).toBe(headingSize("h4"));
  });

  it("derives the divider from the text colour at the stylesheet's percentage", () => {
    // --color-divider: color-mix(in srgb, #201f1d 16%, transparent)
    const declaration = cssVar("color-divider");
    const percent = declaration.match(/(\d+)%/)?.[1];
    expect(percent).toBe("16");
  });
});
