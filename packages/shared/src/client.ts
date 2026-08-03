/**
 * The API client shared by web and mobile.
 *
 * Two rules it exists to enforce:
 *
 * 1. **The access token lives in memory only.** Never `localStorage`, never
 *    `AsyncStorage` — either would let a single XSS or a rooted device walk off
 *    with a working session. It is re-obtained after a reload from the httpOnly
 *    refresh cookie (web) or the secure store (native).
 * 2. **A 401 is recovered once, not looped.** Refreshes are single-flight, so
 *    ten concurrent requests hitting an expired token trigger one refresh, not
 *    ten — and a failed refresh signs out rather than retrying forever.
 */

import type { AuthSession } from "./types";

export interface ApiSuccess<T> {
  ok: true;
  data: T;
  status: number;
}

export interface ApiFailure {
  ok: false;
  error: string;
  code?: string;
  details?: Record<string, unknown>;
  status: number;
}

export type ApiResult<T> = ApiSuccess<T> | ApiFailure;

export interface ApiClientOptions {
  baseUrl: string;
  timeoutMs?: number;
  /**
   * Native clients hold the refresh token themselves and pass it in the body.
   * Browsers leave this unset and rely on the httpOnly cookie.
   */
  isNative?: boolean;
  getRefreshToken?: () => Promise<string | null> | string | null;
  /** May be async; the refresh waits for it so a persisted token is durable
   *  before the single-flight is released. */
  onSession?: (session: AuthSession | null) => void | Promise<void>;
}

const DEFAULT_TIMEOUT_MS = 20_000;
const CSRF_COOKIE = "csrf_token";
const CSRF_HEADER = "X-CSRF-Token";

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}=([^;]*)`),
  );
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export class ApiClient {
  private baseUrl: string;
  private timeoutMs: number;
  private isNative: boolean;
  private accessToken: string | null = null;
  private getRefreshToken: ApiClientOptions["getRefreshToken"];
  private onSession: ApiClientOptions["onSession"];
  /** The in-flight refresh, so concurrent 401s share one attempt. */
  private refreshInFlight: Promise<boolean> | null = null;

  constructor(options: ApiClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.isNative = options.isNative ?? false;
    this.getRefreshToken = options.getRefreshToken;
    this.onSession = options.onSession;
  }

  setAccessToken(token: string | null): void {
    this.accessToken = token;
  }

  hasAccessToken(): boolean {
    return this.accessToken !== null;
  }

  private buildUrl(path: string): string {
    const normalized = path.startsWith("/") ? path : `/${path}`;
    return `${this.baseUrl}${normalized}`;
  }

  private async send<T>(
    path: string,
    init: RequestInit,
    { retryOn401 = true }: { retryOn401?: boolean } = {},
  ): Promise<ApiResult<T>> {
    const headers = new Headers(init.headers);
    if (this.accessToken) {
      headers.set("Authorization", `Bearer ${this.accessToken}`);
    }
    if (init.body !== undefined && !(init.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers.set(CSRF_HEADER, csrf);

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);

    let response: Response;
    try {
      response = await fetch(this.buildUrl(path), {
        ...init,
        headers,
        // Browsers need this for the refresh cookie; harmless on native.
        credentials: "include",
        signal: controller.signal,
      });
    } catch (err) {
      clearTimeout(timer);
      if (err instanceof Error && err.name === "AbortError") {
        return { ok: false, error: "The request timed out.", status: 0 };
      }
      return {
        ok: false,
        error: err instanceof Error ? err.message : "Network error.",
        status: 0,
      };
    }
    clearTimeout(timer);

    // An expired access token is the ordinary case, not an error — refresh
    // once and replay. `retryOn401` stops the refresh call itself recursing.
    if (response.status === 401 && retryOn401 && !path.startsWith("/api/v1/auth/")) {
      const refreshed = await this.refreshSession();
      if (refreshed) {
        return this.send<T>(path, init, { retryOn401: false });
      }
    }

    let body: unknown = null;
    try {
      // Inside the try: a connection dropped mid-body makes `text()` reject,
      // and that rejection used to escape `send` — which is documented as
      // never throwing — leaving useResource's spinner up forever.
      const raw = await response.text();
      if (raw) body = JSON.parse(raw);
    } catch {
      body = null;
    }

    const envelope = body as
      | { data?: T; error?: { code?: string; message?: string; details?: Record<string, unknown> } }
      | null;

    if (response.ok) {
      return { ok: true, data: envelope?.data as T, status: response.status };
    }

    return {
      ok: false,
      error: envelope?.error?.message ?? `Something went wrong (${response.status}).`,
      code: envelope?.error?.code,
      details: envelope?.error?.details,
      status: response.status,
    };
  }

  /** Exchange the refresh token for a new pair. Single-flight. */
  async refreshSession(): Promise<boolean> {
    if (this.refreshInFlight) return this.refreshInFlight;

    this.refreshInFlight = (async () => {
      try {
        const body: Record<string, string> = {};
        if (this.isNative) {
          const token = await this.getRefreshToken?.();
          if (!token) return false;
          body.refresh_token = token;
        }

        const path = this.isNative
          ? "/api/v1/auth/refresh?client=native"
          : "/api/v1/auth/refresh";
        const result = await this.send<AuthSession>(
          path,
          { method: "POST", body: JSON.stringify(body) },
          { retryOn401: false },
        );

        if (!result.ok || !result.data?.access_token) {
          this.accessToken = null;
          // Only an authoritative rejection clears the stored credential. A
          // transport failure (offline: status 0; timeout: AbortError) is
          // indistinguishable here from an expired session, and treating it as
          // one wiped the refresh token from the keychain — so launching the
          // app once in airplane mode signed the user out permanently, even
          // though the server-side token was perfectly valid.
          const rejected =
            result.ok === false && (result.status === 401 || result.status === 403);
          if (rejected) this.onSession?.(null);
          return false;
        }

        this.accessToken = result.data.access_token;
        // Awaited: the caller persists the rotated token here, and releasing
        // the single-flight before that write lands let a later refresh read
        // the OLD token from storage, present it, and trip the server's
        // theft detection — signing the user out for doing nothing wrong.
        await this.onSession?.(result.data);
        return true;
      } finally {
        this.refreshInFlight = null;
      }
    })();

    return this.refreshInFlight;
  }

  get<T>(path: string): Promise<ApiResult<T>> {
    return this.send<T>(path, { method: "GET" });
  }

  post<T>(path: string, body?: unknown): Promise<ApiResult<T>> {
    return this.send<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  patch<T>(path: string, body: unknown): Promise<ApiResult<T>> {
    return this.send<T>(path, { method: "PATCH", body: JSON.stringify(body) });
  }

  put<T>(path: string, body: unknown): Promise<ApiResult<T>> {
    return this.send<T>(path, { method: "PUT", body: JSON.stringify(body) });
  }

  delete<T>(path: string): Promise<ApiResult<T>> {
    return this.send<T>(path, { method: "DELETE" });
  }
}

/**
 * Build a query string from values that may be absent or repeated.
 * Skips `undefined`/`null`/`""` so a cleared filter does not send `?q=`.
 */
export function queryString(
  params: Record<string, string | number | boolean | undefined | null | string[]>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const entry of value) search.append(key, entry);
    } else {
      search.set(key, String(value));
    }
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}
