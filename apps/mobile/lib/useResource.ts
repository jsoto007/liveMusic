/** Fetch-on-mount, ignoring the result of a request whose inputs have changed. */

import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiResult } from "@live-msc/shared";

export function useResource<T>(
  fetcher: () => Promise<ApiResult<T>>,
  deps: readonly unknown[],
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // A re-fetch over content that is already on screen. Kept apart from
  // `loading` so a pull-to-refresh spins the control at the top instead of
  // blanking the page back to a skeleton.
  const [refreshing, setRefreshing] = useState(false);
  const [nonce, setNonce] = useState(0);
  const generation = useRef(0);
  const hasData = useRef(false);

  const reload = useCallback(() => {
    if (hasData.current) setRefreshing(true);
    setNonce((value) => value + 1);
  }, []);

  useEffect(() => {
    const current = ++generation.current;
    setLoading(true);
    void fetcher().then((result) => {
      // A slow response must never overwrite a newer one.
      if (generation.current !== current) return;
      if (result.ok) {
        setData(result.data);
        hasData.current = true;
        setError(null);
      } else {
        setError(result.error);
      }
      setLoading(false);
      setRefreshing(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { data, error, loading, refreshing, reload };
}
