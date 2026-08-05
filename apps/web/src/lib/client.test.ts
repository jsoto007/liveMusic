/**
 * The ApiClient's session handling, tested where it is dangerous.
 *
 * These live in the web app rather than the shared package because that is
 * where a test runner already exists; the code under test is shared by mobile.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient, uploadDirect, UploadError } from "@live-msc/shared";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const ok = (data: unknown) => jsonResponse({ data, error: null });
const fail = (code: string, message: string, status: number) =>
  jsonResponse({ data: null, error: { code, message, details: {} } }, status);

describe("ApiClient", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    // Cookies persist across tests in jsdom, and a stale csrf_token would
    // make later assertions about headers meaningless.
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("unwraps the data envelope on success", async () => {
    fetchMock.mockResolvedValueOnce(ok({ count: 3 }));
    const api = new ApiClient({ baseUrl: "" });

    const result = await api.get<{ count: number }>("/api/v1/events");

    expect(result.ok).toBe(true);
    expect(result.ok && result.data.count).toBe(3);
  });

  it("surfaces the error code and message on failure", async () => {
    fetchMock.mockResolvedValueOnce(fail("LIMIT_REACHED", "Too many samples.", 409));
    const api = new ApiClient({ baseUrl: "" });

    const result = await api.post("/api/v1/uploads", {});

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.code).toBe("LIMIT_REACHED");
      expect(result.error).toBe("Too many samples.");
      expect(result.status).toBe(409);
    }
  });

  it("never writes the access token anywhere but memory", async () => {
    fetchMock.mockResolvedValue(ok({}));
    const api = new ApiClient({ baseUrl: "" });

    api.setAccessToken("a-secret-token");
    await api.get("/api/v1/me");

    // The whole point of holding it in memory: an XSS reading storage or
    // cookies must come away with nothing.
    expect(JSON.stringify(localStorage)).not.toContain("a-secret-token");
    expect(JSON.stringify(sessionStorage)).not.toContain("a-secret-token");
    expect(document.cookie).not.toContain("a-secret-token");
  });

  it("echoes the CSRF cookie back as a header", async () => {
    document.cookie = "csrf_token=abc123; path=/";
    fetchMock.mockResolvedValueOnce(ok({}));
    const api = new ApiClient({ baseUrl: "" });

    await api.post("/api/v1/auth/logout");

    const headers = fetchMock.mock.calls[0]![1].headers as Headers;
    expect(headers.get("X-CSRF-Token")).toBe("abc123");
  });

  it("refreshes once and replays the request after a 401", async () => {
    fetchMock
      .mockResolvedValueOnce(fail("UNAUTHORIZED", "Authentication required.", 401))
      .mockResolvedValueOnce(ok({ access_token: "fresh", user: { id: "u1" } }))
      .mockResolvedValueOnce(ok({ user: { id: "u1" } }));

    const api = new ApiClient({ baseUrl: "" });
    const result = await api.get<{ user: { id: string } }>("/api/v1/me");

    expect(result.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1]![0]).toContain("/api/v1/auth/refresh");

    // The replay must carry the NEW token, not the expired one.
    const replayHeaders = fetchMock.mock.calls[2]![1].headers as Headers;
    expect(replayHeaders.get("Authorization")).toBe("Bearer fresh");
  });

  it("does not loop when the refresh itself fails", async () => {
    fetchMock
      .mockResolvedValueOnce(fail("UNAUTHORIZED", "Authentication required.", 401))
      .mockResolvedValueOnce(fail("SESSION_EXPIRED", "Please sign in again.", 401));

    const api = new ApiClient({ baseUrl: "" });
    const result = await api.get("/api/v1/me");

    expect(result.ok).toBe(false);
    // One original, one refresh. A third call would mean an infinite retry.
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("never tries to refresh a failing auth route", async () => {
    fetchMock.mockResolvedValueOnce(fail("INVALID_CREDENTIALS", "No match.", 401));
    const api = new ApiClient({ baseUrl: "" });

    const result = await api.post("/api/v1/auth/login", { email: "a@b.c" });

    expect(result.ok).toBe(false);
    // A wrong password must not trigger a refresh — that would rotate (and on
    // reuse, revoke) the session of whoever is already signed in.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("collapses concurrent 401s into a single refresh", async () => {
    // Ten expired requests must not present the refresh token ten times: the
    // second presentation of an already-rotated token is treated as theft and
    // revokes the whole family, signing the user out.
    let refreshCount = 0;
    fetchMock.mockImplementation((url: string) => {
      if (String(url).includes("/auth/refresh")) {
        refreshCount += 1;
        return Promise.resolve(ok({ access_token: "fresh", user: { id: "u1" } }));
      }
      return Promise.resolve(
        refreshCount === 0
          ? fail("UNAUTHORIZED", "Authentication required.", 401)
          : ok({ fine: true }),
      );
    });

    const api = new ApiClient({ baseUrl: "" });
    await Promise.all(Array.from({ length: 10 }, () => api.get("/api/v1/me")));

    expect(refreshCount).toBe(1);
  });

  it("reports a timeout rather than hanging", async () => {
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => {
            const error = new Error("aborted");
            error.name = "AbortError";
            reject(error);
          });
        }),
    );

    const api = new ApiClient({ baseUrl: "", timeoutMs: 10 });
    const result = await api.get("/api/v1/events");

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain("timed out");
  });
});

describe("uploadDirect", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  const ticket = {
    upload_id: "up1",
    url: "https://account.r2.cloudflarestorage.com/bucket/artists/audio/a1/abc.mp3",
    key: "artists/audio/a1/abc.mp3",
    headers: { "Content-Type": "audio/mpeg" },
    max_bytes: 1000,
    expires_at: "2026-01-01T00:00:00Z",
  };

  const request = {
    purpose: "artist_audio" as const,
    targetId: "a1",
    contentType: "audio/mpeg",
    sizeBytes: 100,
  };

  it("sends the file to R2, not to the API", async () => {
    fetchMock
      .mockResolvedValueOnce(ok(ticket))
      .mockResolvedValueOnce(new Response(null, { status: 200 }))
      .mockResolvedValueOnce(ok({ sample: { id: "s1" } }));

    const api = new ApiClient({ baseUrl: "" });
    await uploadDirect(api, request, new Blob(["audio"]));

    const storageCall = fetchMock.mock.calls[1]!;
    expect(storageCall[0]).toBe(ticket.url);
    expect(storageCall[1].method).toBe("PUT");
    expect(storageCall[1].body).toBeInstanceOf(Blob);
    // Our bearer token must never be sent to a third-party origin.
    expect(storageCall[1].credentials).toBe("omit");
  });

  it("PUTs with the exact headers the server signed, notably Content-Type", async () => {
    fetchMock
      .mockResolvedValueOnce(ok(ticket))
      .mockResolvedValueOnce(new Response(null, { status: 200 }))
      .mockResolvedValueOnce(ok({ sample: { id: "s1" } }));

    const api = new ApiClient({ baseUrl: "" });
    await uploadDirect(api, request, new Blob(["audio"]));

    const storageCall = fetchMock.mock.calls[1]!;
    expect(storageCall[1].headers).toEqual(ticket.headers);
  });

  it("abandons the ticket when the storage upload fails", async () => {
    fetchMock
      .mockResolvedValueOnce(ok(ticket))
      .mockResolvedValueOnce(new Response("too big", { status: 400 }))
      .mockResolvedValueOnce(ok({ abandoned: true }));

    const api = new ApiClient({ baseUrl: "" });

    await expect(uploadDirect(api, request, new Blob(["x"]))).rejects.toBeInstanceOf(
      UploadError,
    );

    // Without this the orphaned object sits in the bucket until it expires.
    const cleanup = fetchMock.mock.calls[2]!;
    expect(cleanup[0]).toContain("/api/v1/uploads/up1");
    expect(cleanup[1].method).toBe("DELETE");
  });

  it("does not upload anything when the ticket is refused", async () => {
    fetchMock.mockResolvedValueOnce(fail("LIMIT_REACHED", "Quota reached.", 409));
    const api = new ApiClient({ baseUrl: "" });

    await expect(uploadDirect(api, request, new Blob(["x"]))).rejects.toThrow(
      "Quota reached.",
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("ApiClient session durability", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  it("does not discard the stored credential on a network failure", async () => {
    // Regression: any non-ok result cleared the session, and a thrown fetch
    // (offline) is reported as {ok:false, status:0} — indistinguishable from a
    // 401 at that point. On mobile this wiped the keychain, so launching once
    // in airplane mode signed the user out for good.
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const onSession = vi.fn();

    const api = new ApiClient({
      baseUrl: "",
      isNative: true,
      getRefreshToken: () => "a-valid-refresh-token",
      onSession,
    });

    expect(await api.refreshSession()).toBe(false);
    expect(onSession).not.toHaveBeenCalled();
  });

  it("does not discard the credential on a timeout either", async () => {
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => {
            const error = new Error("aborted");
            error.name = "AbortError";
            reject(error);
          });
        }),
    );
    const onSession = vi.fn();

    const api = new ApiClient({
      baseUrl: "",
      timeoutMs: 10,
      isNative: true,
      getRefreshToken: () => "a-valid-refresh-token",
      onSession,
    });

    expect(await api.refreshSession()).toBe(false);
    expect(onSession).not.toHaveBeenCalled();
  });

  it("DOES discard the credential when the server rejects it", async () => {
    fetchMock.mockResolvedValue(fail("SESSION_EXPIRED", "Please sign in again.", 401));
    const onSession = vi.fn();

    const api = new ApiClient({
      baseUrl: "",
      isNative: true,
      getRefreshToken: () => "a-revoked-token",
      onSession,
    });

    expect(await api.refreshSession()).toBe(false);
    expect(onSession).toHaveBeenCalledWith(null);
  });

  it("waits for the rotated token to be persisted before releasing", async () => {
    // Releasing the single-flight before the keychain write landed let a later
    // refresh read the OLD token, present it, and trip theft detection.
    const writes: string[] = [];
    let resolvePersist: (() => void) | null = null;

    fetchMock.mockResolvedValue(
      ok({ access_token: "fresh", refresh_token: "rotated", user: { id: "u1" } }),
    );

    const api = new ApiClient({
      baseUrl: "",
      isNative: true,
      getRefreshToken: () => "original",
      onSession: async (session) => {
        await new Promise<void>((resolve) => {
          resolvePersist = resolve;
        });
        writes.push(session?.refresh_token ?? "cleared");
      },
    });

    const inFlight = api.refreshSession();
    // Let the fetch and body-read microtasks drain so onSession is entered.
    for (let tick = 0; tick < 20 && resolvePersist === null; tick += 1) {
      await Promise.resolve();
    }
    expect(resolvePersist).not.toBeNull();
    expect(writes).toEqual([]); // entered the persist, not finished it

    resolvePersist!();
    expect(await inFlight).toBe(true);
    expect(writes).toEqual(["rotated"]);
  });

  it("survives a response body that fails mid-read", async () => {
    // `response.text()` rejecting used to escape send() — which is documented
    // as never throwing — and left the caller's spinner up forever.
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      text: () => Promise.reject(new Error("connection reset")),
    } as unknown as Response);

    const api = new ApiClient({ baseUrl: "" });
    const result = await api.get("/api/v1/events");

    expect(result.ok).toBe(true);
    expect(result.ok && result.data).toBeUndefined();
  });
});
