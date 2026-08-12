/**
 * Every genre must have its house stock plate on disk: the fallback is what
 * guarantees no listing ever prints without a photograph, so a genre added to
 * the shared list without a matching file in `public/stock/` is a bug this
 * test exists to catch before a reader does.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { GENRES, STOCK_POSTERS } from "@live-msc/shared";
import { describe, expect, it } from "vitest";

import { stockPosterUrl } from "./stock";

// Resolved from the vitest working directory (apps/web).
const stockDir = resolve(process.cwd(), "public", "stock");

describe("the house stock plates", () => {
  it("cover every genre with a real file of sensible weight", () => {
    for (const { value } of GENRES) {
      const file = STOCK_POSTERS[value];
      expect(file, `genre ${value} has no stock poster entry`).toBeTruthy();
      const bytes = readFileSync(resolve(stockDir, file));
      expect(bytes.byteLength, `${file} is empty`).toBeGreaterThan(0);
      // These are row thumbs and a mid-column plate, not hero art; a
      // derivative that grows past this is a regression in the export step.
      expect(bytes.byteLength, `${file} is too heavy to serve`).toBeLessThan(512 * 1024);
      // JPEG magic bytes — the plate must actually be an image, not an
      // HTML error page saved with a .jpg name.
      expect(bytes[0], `${file} is not a JPEG`).toBe(0xff);
      expect(bytes[1], `${file} is not a JPEG`).toBe(0xd8);
    }
  });

  it("map to no genre twice", () => {
    const files = GENRES.map(({ value }) => STOCK_POSTERS[value]);
    expect(new Set(files).size).toBe(files.length);
  });

  it("resolve to the public path the app serves", () => {
    expect(stockPosterUrl("jazz")).toBe("/stock/jazz.jpg");
  });
});
