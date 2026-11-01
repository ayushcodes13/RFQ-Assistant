"""Server-only, signed single-operator workspace gate.

This deliberately does NOT implement multi-user identity or tenant isolation.
"""
import { createHash, createHmac, randomBytes, timingSafeEqual } from "node:crypto";

export const WORKSPACE_COOKIE = "rfq_workspace_session";
const SESSION_SECONDS = 8 * 60 * 60;
const COOKIE_VERSION = "v1";

function enabled(): boolean {
  return process.env.NODE_ENV === "production"
    || !!process.env.RFQ_ASSISTANT_API_KEY
    || !!process.env.RFQ_WORKSPACE_PASSWORD
    || !!process.env.RFQ_WORKSPACE_SESSION_SECRET;
}

function config(): { password: string; secret: string } | null {
  const password = process.env.RFQ_WORKSPACE_PASSWORD || "";
  const secret = process.env.RFQ_WORKSPACE_SESSION_SECRET || "";
  if (password.length < 16 || secret.length < 32) return null;
  return { password, secret };
}

export function workspaceAuthStatus(cookie?: string): "open" | "misconfigured" | "authenticated" | "unauthenticated" {
  if (!enabled()) return "open";
  const pair = config();
  if (!pair) return "misconfigured";
  return cookie && verifySession(cookie, pair.secret) ? "authenticated" : "unauthenticated";
}

function signature(secret: string, payload: string): Buffer {
  return createHmac("sha256", secret).update(payload).digest();
}

export function issueSession(): string | null {
  const pair = config();
  if (!pair || !enabled()) return null;
  const expiry = Math.floor(Date.now() / 1000) + SESSION_SECONDS;
  const payload = `${COOKIE_VERSION}.${expiry}.${randomBytes(16).toString("hex")}`;
  return `${payload}.${signature(pair.secret, payload).toString("base64url")}`;
}

function verifySession(token: string, secret: string): boolean {
  const match = /^(v1)\.(\d{10})\.([0-9a-f]{32})\.([a-zA-Z0-9_-]{43})$/.exec(token);
  if (!match) return false;
  const expiry = Number(match[2]);
  const now = Math.floor(Date.now() / 1000);
  if (!Number.isSafeInteger(expiry) || expiry <= now || expiry > now + SESSION_SECONDS) return false;
  const payload = `${match[1]}.${match[2]}.${match[3]}`;
  const expected = signature(secret, payload);
  const actual = Buffer.from(match[4], "base64url");
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}

export function verifyWorkspacePassword(candidate: string): boolean {
  const pair = config();
  if (!pair || !enabled() || typeof candidate !== "string") return false;
  const supplied = createHash("sha256").update(candidate).digest();
  const actual = createHash("sha256").update(pair.password).digest();
  return timingSafeEqual(supplied, actual);
}

export function sessionCookieOptions() {
  return { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "strict" as const, path: "/", maxAge: SESSION_SECONDS };
}
