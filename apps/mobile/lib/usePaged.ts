/**
 * Fetch-and-append pagination over a `{limit, offset}` endpoint.
 *
 * Page zero replaces (the `useResource` behaviour); `loadMore` appends the
 * next page. A response from a superseded request — the inputs changed, or a
 * reload landed first — is dropped, never merged.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiResult } from "@live-msc/shared";

/** The normalised page shape; each caller maps its endpoint's keys into it. */
export interface Page<T> {
  items: T[];
  total: number;
  hasMore: boolean;
}

export function usePaged<T>(
  fetchPage: (offset: number) => Promise<ApiResult<Page<T>>>,
  deps: readonly unknown[],
) {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const generation = useRef(0);
  // Read through refs so `loadMore` keeps a stable identity while always
  // calling the closure the latest render built, over the latest items.
  const fetcher = useRef(fetchPage);
  fetcher.current = fetchPage;
  const itemsRef = useRef<T[]>([]);
  itemsRef.current = items;
  const busyRef = useRef(false);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    const current = ++generation.current;
    setLoading(true);
    void fetcher.current(0).then((result) => {
      // A slow response must never overwrite a newer one.
      if (generation.current !== current) return;
      if (result.ok && result.data) {
        setItems(result.data.items);
        setTotal(result.data.total);
        setHasMore(result.data.hasMore);
        setError(null);
      } else if (!result.ok) {
        setError(result.error);
      }
      setLoading(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const loadMore = useCallback(async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    const current = generation.current;
    setLoadingMore(true);
    try {
      const result = await fetcher.current(itemsRef.current.length);
      // A page-zero refetch superseded this append; drop it on the floor.
      if (generation.current !== current) return;
      if (result.ok && result.data) {
        const next = result.data;
        setItems((previous) => [...previous, ...next.items]);
        setTotal(next.total);
        setHasMore(next.hasMore);
      } else if (!result.ok) {
        setError(result.error);
      }
    } finally {
      // Cleared even for a dropped response — the button must not stay
      // stuck on "Fetching…" after a reload wins the race.
      setLoadingMore(false);
      busyRef.current = false;
    }
  }, []);

  /** Edit loaded items in place — a like toggled, a row marked read. */
  const mutate = useCallback((map: (current: T[]) => T[]) => setItems(map), []);

  return { items, total, hasMore, loading, loadingMore, error, reload, loadMore, mutate };
}
