/**
 * Session state for the native app.
 *
 * The access token lives in memory inside the ApiClient. The refresh token —
 * the only long-lived credential — goes to `expo-secure-store`, which is the
 * Keychain on iOS and EncryptedSharedPreferences on Android. It never touches
 * AsyncStorage, which is plaintext on disk and readable on a rooted device.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import * as SecureStore from "expo-secure-store";
import { ApiClient, type Artist, type AuthSession, type User } from "@live-msc/shared";

import { API_BASE_URL } from "./config";

const REFRESH_KEY = "live_msc.refresh_token";

// The most recently issued token, held in memory as the authoritative value.
// The keychain write is durable storage, but reading back from it during a
// rotation raced the write and could hand back the already-rotated token —
// which the server correctly treats as theft and answers by revoking the whole
// family. In-memory first, keychain as the cold-start fallback.
let cachedRefreshToken: string | null = null;

async function readRefreshToken(): Promise<string | null> {
  if (cachedRefreshToken) return cachedRefreshToken;
  try {
    cachedRefreshToken = await SecureStore.getItemAsync(REFRESH_KEY);
    return cachedRefreshToken;
  } catch {
    // A device with no secure hardware, or a keychain the OS refused. Treat it
    // as "no session" rather than crashing the app on launch.
    return null;
  }
}

async function writeRefreshToken(token: string | null): Promise<void> {
  cachedRefreshToken = token;
  try {
    if (token) {
      await SecureStore.setItemAsync(REFRESH_KEY, token, {
        keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
      });
    } else {
      await SecureStore.deleteItemAsync(REFRESH_KEY);
    }
  } catch {
    // Failing to persist means the session ends when the app does, which is
    // an acceptable degradation. Failing loudly here would block sign-in.
  }
}

export const api = new ApiClient({
  baseUrl: API_BASE_URL,
  isNative: true,
  getRefreshToken: readRefreshToken,
  onSession: async (session) => {
    // Awaited by the client before it releases the single-flight refresh, so
    // the next rotation cannot read a stale token.
    await writeRefreshToken(session?.refresh_token ?? null);
  },
});

interface AuthState {
  user: User | null;
  artists: Artist[];
  initializing: boolean;
  signIn: (email: string, password: string) => Promise<string | null>;
  register: (input: {
    email: string;
    password: string;
    displayName: string;
    homeCity?: string;
  }) => Promise<string | null>;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [artists, setArtists] = useState<Artist[]>([]);
  const [initializing, setInitializing] = useState(true);

  const loadProfile = useCallback(async () => {
    const result = await api.get<{ user: User; artists: Artist[] }>("/api/v1/me");
    if (result.ok && result.data) {
      setUser(result.data.user);
      setArtists(result.data.artists ?? []);
    } else {
      setUser(null);
      setArtists([]);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const restored = await api.refreshSession();
      if (cancelled) return;
      if (restored) await loadProfile();
      if (!cancelled) setInitializing(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [loadProfile]);

  const adopt = useCallback(async (session: AuthSession) => {
    api.setAccessToken(session.access_token);
    await writeRefreshToken(session.refresh_token ?? null);
    setUser(session.user);
  }, []);

  const signIn = useCallback<AuthState["signIn"]>(
    async (email, password) => {
      const result = await api.post<AuthSession>("/api/v1/auth/login?client=native", {
        email,
        password,
      });
      if (!result.ok || !result.data) return result.ok ? "Could not sign in." : result.error;
      await adopt(result.data);
      await loadProfile();
      return null;
    },
    [adopt, loadProfile],
  );

  const register = useCallback<AuthState["register"]>(
    async ({ email, password, displayName, homeCity }) => {
      const result = await api.post<AuthSession>("/api/v1/auth/register?client=native", {
        email,
        password,
        display_name: displayName,
        home_city: homeCity,
      });
      if (!result.ok || !result.data) {
        return result.ok ? "Could not create the account." : result.error;
      }
      await adopt(result.data);
      await loadProfile();
      return null;
    },
    [adopt, loadProfile],
  );

  const signOut = useCallback(async () => {
    const token = await readRefreshToken();
    // Tell the server to revoke the family; a token that only disappears from
    // the device stays valid to anyone who copied it.
    await api.post("/api/v1/auth/logout", token ? { refresh_token: token } : {});
    await writeRefreshToken(null);
    api.setAccessToken(null);
    setUser(null);
    setArtists([]);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, artists, initializing, signIn, register, signOut, refreshProfile: loadProfile }),
    [user, artists, initializing, signIn, register, signOut, loadProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside an AuthProvider.");
  return context;
}
