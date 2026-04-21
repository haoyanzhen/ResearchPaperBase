import { http, tokenStore } from "./client";
import type {
  ISODateString,
  User,
} from "../types";

// ── Request / Response 类型（对齐 api.md 第 1 节）─────────────────────────────

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
}

export interface RegisterResponse {
  user_id: string;
  username: string;
  email: string;
  created_at: ISODateString;
}

export interface LoginRequest {
  credential: string;  // 用户名或邮箱
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: { user_id: string; username: string; email: string };
}

export interface MeResponse {
  user_id: string;
  username: string;
  email: string;
  created_at: ISODateString;
}

export interface UpdateMeRequest {
  username?: string;
  email?: string;
  password?: string;
}

// ── API 方法 ──────────────────────────────────────────────────────────────────

export const authApi = {
  register: (body: RegisterRequest) =>
    http.post<RegisterResponse>("/auth/register", body),

  login: async (body: LoginRequest): Promise<LoginResponse> => {
    const data = await http.post<LoginResponse>("/auth/login", body);
    tokenStore.set(data.access_token);
    return data;
  },

  logout: async (): Promise<void> => {
    await http.post("/auth/logout");
    tokenStore.clear();
  },

  me: () => http.get<MeResponse>("/auth/me"),

  updateMe: (body: UpdateMeRequest) =>
    http.patch<MeResponse>("/auth/me", body),
};
