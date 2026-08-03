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
  const [nonce, setNonce] = useState(0);
  const generation = useRef(0);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    const current = ++generation.current;
    setLoading(true);
    void fetcher().then((result) => {
      // A slow response must never overwrite a newer one.
      if (generation.current !== current) return;
      if (result.ok) {
        setData(result.data);
        setError(null);
      } else {
        setError(result.error);
      }
      setLoading(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { data, error, loading, reload };
}
