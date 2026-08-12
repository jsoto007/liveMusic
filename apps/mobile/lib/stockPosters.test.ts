/**
 * Guards the promise made in `stockPosters.ts`: the bundled stock plates are
 * the SAME files the web serves from `public/stock/`, one per genre. The map
 * is written out by hand (Metro needs literal asset paths), so this test is
 * what keeps it complete when a genre is added and keeps the two platforms'
 * photographs from drifting apart — the same lockstep contract
 * `theme.test.ts` enforces for the design tokens.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { GENRES, STOCK_POSTERS } from "@live-msc/shared";
import { describe, expect, it } from "vitest";

// Resolved from the vitest working directory (apps/mobile), like theme.test.ts.
const mobileStockDir = resolve(process.cwd(), "assets", "stock");
const webStockDir = resolve(process.cwd(), "../web/public/stock");
const mapSource = readFileSync(resolve(process.cwd(), "lib", "stockPosters.ts"), "utf8");

describe("the bundled stock plates match the web's", () => {
  it("bundles every genre's file, byte for byte the web's copy", () => {
    for (const { value } of GENRES) {
      const file = STOCK_POSTERS[value];
      const bundled = readFileSync(resolve(mobileStockDir, file));
      const served = readFileSync(resolve(webStockDir, file));
      expect(bundled.equals(served), `${file} differs between mobile and web`).toBe(true);
    }
  });

  it("declares every genre in the hand-written Metro asset map", () => {
    for (const { value } of GENRES) {
      // The import line is the part Metro resolves; its presence per genre is
      // what a forgotten map entry would be missing. (The record itself is
      // exhaustively typed, so a present import wired to the wrong key is
      // already a compile error.)
      expect(
        mapSource.includes(`"../assets/stock/${STOCK_POSTERS[value]}"`),
        `stockPosters.ts does not import the ${value} plate`,
      ).toBe(true);
    }
  });
});
