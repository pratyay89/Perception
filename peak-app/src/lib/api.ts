import axios, { AxiosError } from "axios";
import { clearSession, getSession } from "@/lib/auth";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api";

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Send the access token with every request.
api.interceptors.request.use((config) => {
  const session = getSession();
  if (session) {
    config.headers.Authorization = `Bearer ${session.token}`;
  }
  return config;
});

// A 401 means the token is missing, expired or no longer valid: log out.
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const url = error.config?.url || "";
    const isLoginCall = url.includes("/auth/login");
    if (error.response?.status === 401 && !isLoginCall) {
      clearSession();
      if (
        typeof window !== "undefined" &&
        !window.location.pathname.startsWith("/login")
      ) {
        window.location.assign("/login");
      }
    }
    return Promise.reject(error);
  }
);

/**
 * A readable message for a failed request.
 *
 * FastAPI puts a string in `detail` for most errors, and a list of
 * `{loc, msg}` objects for validation errors (HTTP 422).
 */
export function errorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      return "Cannot reach the server. Is the backend running?";
    }
    const detail = (error.response.data as { detail?: unknown } | undefined)
      ?.detail;
    if (typeof detail === "string" && detail) return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { loc?: unknown[]; msg?: string };
      const field = Array.isArray(first.loc)
        ? first.loc.filter((part) => part !== "body").join(" → ")
        : "";
      const msg = first.msg || fallback;
      return field ? `${field}: ${msg}` : msg;
    }
  }
  return fallback;
}
