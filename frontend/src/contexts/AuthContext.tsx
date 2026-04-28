import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  authApi,
  type LoginRequest,
  type MeResponse,
  type RegisterRequest,
} from "../../api/auth";
import { tokenStore } from "../../api/client";

type AuthContextValue = {
  user: MeResponse | null;
  initializing: boolean;
  login: (payload: LoginRequest) => Promise<void>;
  register: (payload: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  setUser: (user: MeResponse | null) => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [initializing, setInitializing] = useState(true);

  const refreshUser = useCallback(async () => {
    const me = await authApi.me();
    setUser(me);
  }, []);

  useEffect(() => {
    const boot = async () => {
      const token = tokenStore.get();
      if (!token) {
        setInitializing(false);
        return;
      }
      try {
        await refreshUser();
      } catch {
        tokenStore.clear();
        setUser(null);
      } finally {
        setInitializing(false);
      }
    };
    void boot();
  }, [refreshUser]);

  const login = useCallback(async (payload: LoginRequest) => {
    try {
      await authApi.login(payload);
      await refreshUser();
    } catch (error) {
      tokenStore.clear();
      setUser(null);
      throw error;
    }
  }, [refreshUser]);

  const register = useCallback(async (payload: RegisterRequest) => {
    await authApi.register(payload);
    await login({ credential: payload.username, password: payload.password });
  }, [login]);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      tokenStore.clear();
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({
      user,
      initializing,
      login,
      register,
      logout,
      refreshUser,
      setUser,
    }),
    [initializing, login, logout, refreshUser, register, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return value;
}
