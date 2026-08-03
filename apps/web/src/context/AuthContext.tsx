/**
 * Session state.
 *
 * The access token is held by the ApiClient in memory and never mirrored into
 * storage. On mount the app attempts one silent refresh — if the httpOnly
 * cookie is still valid the reader stays signed in across a reload; if not,
 * they are simply signed out, which is the correct outcome.
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
import type { Artist, AuthSession, User } from "@live-msc/shared";

import { api } from "../lib/api";

interface AuthState {
  user: User | null;
  artists: Artist[];
  /** True until the initial silent refresh settles, so guarded routes wait. */
  initializing: boolean;
  signIn: (email: string, password: string) => Promise<string | null>;
  register: (input: RegisterInput) => Promise<string | null>;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

export interface RegisterInput {
  email: string;
  password: string;
  displayName: string;
  homeCity?: string;
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

  const adoptSession = useCallback((session: AuthSession) => {
    api.setAccessToken(session.access_token);
    setUser(session.user);
  }, []);

  const signIn = useCallback<AuthState["signIn"]>(
    async (email, password) => {
      const result = await api.post<AuthSession>("/api/v1/auth/login", { email, password });
      if (!result.ok || !result.data) {
        return result.ok ? "Could not sign in." : result.error;
      }
      adoptSession(result.data);
      await loadProfile();
      return null;
    },
    [adoptSession, loadProfile],
  );

  const register = useCallback<AuthState["register"]>(
    async ({ email, password, displayName, homeCity }) => {
      const result = await api.post<AuthSession>("/api/v1/auth/register", {
        email,
        password,
        display_name: displayName,
        home_city: homeCity,
      });
      if (!result.ok || !result.data) {
        return result.ok ? "Could not create the account." : result.error;
      }
      adoptSession(result.data);
      await loadProfile();
      return null;
    },
    [adoptSession, loadProfile],
  );

  const signOut = useCallback(async () => {
    await api.post("/api/v1/auth/logout");
    api.setAccessToken(null);
    setUser(null);
    setArtists([]);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      artists,
      initializing,
      signIn,
      register,
      signOut,
      refreshProfile: loadProfile,
    }),
    [user, artists, initializing, signIn, register, signOut, loadProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside an AuthProvider.");
  }
  return context;
}
