import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, getToken, setToken } from "./api";
import type { Session } from "./types";

interface AuthState {
  session: Session | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (input: {
    email: string;
    password: string;
    full_name: string;
    organization_name: string;
    title?: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(getToken()));

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setSession(null);
      setLoading(false);
      return;
    }
    try {
      const next = await api.get<Session>("/auth/me");
      setSession(next);
    } catch {
      setSession(null);
      setToken(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const onExpired = () => setSession(null);
    window.addEventListener("auth:expired", onExpired);
    return () => window.removeEventListener("auth:expired", onExpired);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const next = await api.post<Session>("/auth/login", { email, password });
    setToken(next.access_token);
    setSession(next);
  }, []);

  const register = useCallback(
    async (input: {
      email: string;
      password: string;
      full_name: string;
      organization_name: string;
      title?: string;
    }) => {
      const next = await api.post<Session>("/auth/register", input);
      setToken(next.access_token);
      setSession(next);
    },
    [],
  );

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      // ignore - the local session is cleared either way
    }
    setToken(null);
    setSession(null);
  }, []);

  const value = useMemo(
    () => ({ session, loading, login, register, logout, refresh }),
    [session, loading, login, register, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
