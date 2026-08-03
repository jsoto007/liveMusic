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

interface ResourceState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

export function useResource<T>(
  fetcher: () => Promise<ApiResult<T>>,
  deps: readonly unknown[],
): ResourceState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  // Incremented on every run; a response whose generation is stale is ignored.
  const generation = useRef(0);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    const current = ++generation.current;
    setLoading(true);

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
  }, [...deps, nonce]);

  return { data, error, loading, reload };
}
