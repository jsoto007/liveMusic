/**
 * A small fetch-on-mount hook.
 *
 * Deliberately not a data-fetching library: the app has a handful of read
 * endpoints and no cross-screen cache to invalidate. The one thing it does
 * carefully is drop the result of a request whose inputs have since changed,
 * so a slow response cannot overwrite a newer one.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiResult } from "@live-msc/shared";

interface ResourceOptions {
  /**
   * Hold the fetch until this is true. The case it exists for: a response
   * whose *content* depends on who is asking. On a hard load the session is
   * restored asynchronously (one silent refresh), so a request fired on mount
   * goes out unauthenticated and comes back as the anonymous view — the
   * reader's own saved state, and their permission to edit, quietly missing
   * with nothing to retry it.
   *
   * Waiting costs one round trip. Fetching twice would work too, but it shows
   * the reader the anonymous answer first and then swaps it, which is worse
   * than a moment of spinner.
   */
  enabled?: boolean;
}

interface ResourceState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

export function useResource<T>(
  fetcher: () => Promise<ApiResult<T>>,
  deps: readonly unknown[],
  options: ResourceOptions = {},
): ResourceState<T> {
  const enabled = options.enabled ?? true;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  // Incremented on every run; a response whose generation is stale is ignored.
  const generation = useRef(0);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    // Incremented even when disabled, so a response still in flight from
    // before cannot land after the inputs have moved on.
    const current = ++generation.current;
    setLoading(true);
    if (!enabled) return;

    void fetcher().then((result) => {
      if (generation.current !== current) return;
      if (result.ok) {
        setData(result.data);
        setError(null);
      } else {
        setError(result.error);
      }
      setLoading(false);
    });
    // `fetcher` is rebuilt on every render by design; the caller's `deps` are
    // the real inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, enabled]);

  return { data, error, loading, reload };
}
