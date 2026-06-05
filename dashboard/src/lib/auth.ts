import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { createSessionToken, verifyPasswordHash, verifySessionToken } from "./auth-core";

const COOKIE_NAME = "watchdog_session";
const SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;

export async function verifyLoginPassword(password: string): Promise<boolean> {
  return verifyPasswordHash(password, process.env.DASHBOARD_PASSWORD_HASH);
}

export async function createSessionCookie(): Promise<void> {
  const secret = process.env.DASHBOARD_SESSION_SECRET;
  if (!secret) {
    throw new Error("DASHBOARD_SESSION_SECRET is not configured.");
  }
  const store = await cookies();
  store.set(COOKIE_NAME, createSessionToken(secret), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: SESSION_MAX_AGE_SECONDS,
    path: "/",
  });
}

export async function clearSessionCookie(): Promise<void> {
  const store = await cookies();
  store.delete(COOKIE_NAME);
}

export async function hasValidSession(): Promise<boolean> {
  const store = await cookies();
  const token = store.get(COOKIE_NAME)?.value;
  return verifySessionToken(token, process.env.DASHBOARD_SESSION_SECRET, SESSION_MAX_AGE_SECONDS * 1000);
}

export async function requireSession(): Promise<void> {
  if (!(await hasValidSession())) {
    redirect("/login");
  }
}
