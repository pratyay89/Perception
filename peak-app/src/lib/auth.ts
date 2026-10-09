"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { LoginResponse, Role } from "@/lib/types";

const STORAGE_KEY = "perception:session";

export interface Session {
  token: string;
  email: string;
  role: Role;
  fullName: string;
}

/** Expiry time (ms since epoch) stored in the JWT, or null if unreadable. */
function tokenExpiry(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const exp = JSON.parse(json).exp;
    return typeof exp === "number" ? exp * 1000 : null;
  } catch {
    return null;
  }
}

export function getSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as Session;
    if (!session.token || !session.email || !session.role) return null;

    const expiry = tokenExpiry(session.token);
    if (expiry !== null && expiry <= Date.now()) {
      window.localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export function saveSession(login: LoginResponse): Session {
  const session: Session = {
    token: login.access_token,
    email: login.email,
    role: login.role,
    fullName: login.full_name,
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  return session;
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
}

/**
 * The logged-in user, for pages that need one.
 *
 * While `loading` is true the session is not known yet (it lives in
 * localStorage, which only exists in the browser). When there is no session,
 * or it has the wrong role, the user is sent to `redirectTo`.
 */
export function useSession(options: { role?: Role } = {}): {
  session: Session | null;
  loading: boolean;
} {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const { role } = options;

  useEffect(() => {
    const current = getSession();
    if (!current) {
      router.replace("/login");
      return;
    }
    if (role && current.role !== role) {
      router.replace("/dashboard");
      return;
    }
    setSession(current);
    setLoading(false);
  }, [router, role]);

  return { session, loading };
}
