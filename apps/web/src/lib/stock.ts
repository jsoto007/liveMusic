/**
 * The house stock plates — the fallback photograph for a listing with no
 * uploaded poster. Files live in `public/stock/`, one per genre, named by the
 * genre's wire value; `src/lib/stock.test.ts` asserts the set stays complete.
 */

import { STOCK_POSTERS, type Genre } from "@live-msc/shared";
import type { SyntheticEvent } from "react";

export function stockPosterUrl(genre: Genre): string {
  return `/stock/${STOCK_POSTERS[genre]}`;
}

/**
 * `onError` handler for poster `<img>`s. Poster URLs are short-lived presigned
 * GETs (they expire in minutes), so a page left open must degrade to the house
 * stock rather than to a broken-image glyph.
 */
export function fallBackToStock(
  event: SyntheticEvent<HTMLImageElement>,
  genre: Genre,
): void {
  const img = event.currentTarget;
  const stock = stockPosterUrl(genre);
  if (!img.src.endsWith(stock)) img.src = stock;
}
