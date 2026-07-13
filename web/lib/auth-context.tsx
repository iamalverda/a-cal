/** Auth context — provides current user state to the entire app.

On mount, checks /api/a-cal/auth/me to see if the user has an active
session. If the backend is reachable but no session exists, attempts
an auto demo-login (standalone/dev mode). If the backend is unreachable,
falls through to demo mode with mock data.
 */

"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import { authApi } from "@/lib/api";
import type { AuthUser } from "@/types";

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  /** True when the backend is unreachable — app falls through to demo mode. */
  backendDown: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [backendDown, setBackendDown] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function initAuth() {
      try {
        const { user: existing, backendDown: down } = await authApi.me();
        if (cancelled) return;

        if (existing) {
          setUser(existing);
          setBackendDown(false);
          return;
        }

        if (down) {
          // Backend unreachable — demo mode with mock data
          setBackendDown(true);
          return;
        }

        // Backend is up but no session — try demo auto-login
        try {
          const demoUser = await authApi.demoLogin();
          if (!cancelled) {
            setUser(demoUser);
            setBackendDown(false);
          }
        } catch {
          // Demo login failed — show login panel
          if (!cancelled) {
            setUser(null);
            setBackendDown(false);
          }
        }
      } catch {
        if (!cancelled) {
          setBackendDown(true);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    initAuth();
    return () => { cancelled = true; };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const u = await authApi.login(email, password);
    setUser(u);
  }, []);

  const register = useCallback(
    async (email: string, password: string, displayName?: string) => {
      const u = await authApi.register(email, password, displayName);
      setUser(u);
    },
    [],
  );

  const logout = useCallback(async () => {
    await authApi.logout();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, backendDown, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
