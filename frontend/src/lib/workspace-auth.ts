/** Encrypted, per-user API-key session for the existing single workspace.
 * This deliberately does NOT implement organization ownership or tenant isolation.
 */
import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";

export const WORKSPACE_COOKIE = "rfq_workspace_session";
const SESSION_SECONDS = 8 * 60 * 60;
const COOKIE_VERSION = "v2";
const VALID_ROLES = new Set(["admin", "reviewer", "viewer"]);

export type WorkspaceUser = { user_id: string; name: string; role: string };
export type WorkspaceSession = WorkspaceUser & { apiKey: string; expiresAt: number };

function enabled(): boolean {
  return process.env.NODE_ENV === "production"
    || !!process.env.RFQ_ASSISTANT_API_KEY
    || !!process.env.RFQ_WORKSPACE_PASSWORD
    || !!process.env.PILOT_API_KEYS
    || !!process.env.RFQ_WORKSPACE_SESSION_SECRET;
}

function sessionSecret(): string | null {
  const secret = process.env.RFQ_WORKSPACE_SESSION_SECRET || "";
  return secret.length >= 32 ? secret : null;
}

function encryptionKey(secret: string): Buffer {
  return createHash("sha256")
    .update("rfq-assistant-workspace-session-v2\0", "utf8")
    .update(secret, "utf8")
    .digest();
}

export function workspaceAuthStatus(cookie?: string): "open" | "misconfigured" | "authenticated" | "unauthenticated" {
  if (!enabled()) return "open";
  if (!sessionSecret()) return "misconfigured";
  return cookie && readWorkspaceSession(cookie) ? "authenticated" : "unauthenticated";
}

export function createWorkspaceSession(apiKey: string, user: WorkspaceUser): string | null {
  const secret = sessionSecret();
  if (!secret || apiKey.length < 16 || apiKey.length > 1024) return null;
  if (!user.user_id || user.user_id.length > 128 || !user.name || user.name.length > 128 || !VALID_ROLES.has(user.role)) return null;

  const expiresAt = Math.floor(Date.now() / 1000) + SESSION_SECONDS;
  const session: WorkspaceSession = { ...user, apiKey, expiresAt };
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", encryptionKey(secret), iv);
  cipher.setAAD(Buffer.from(COOKIE_VERSION, "utf8"));
  const ciphertext = Buffer.concat([
    cipher.update(JSON.stringify(session), "utf8"),
    cipher.final(),
  ]);
  const tag = cipher.getAuthTag();
  return [COOKIE_VERSION, iv.toString("base64url"), tag.toString("base64url"), ciphertext.toString("base64url")].join(".");
}

export function readWorkspaceSession(token: string): WorkspaceSession | null {
  const secret = sessionSecret();
  if (!secret || token.length > 4096) return null;
  const parts = token.split(".");
  if (parts.length !== 4 || parts[0] !== COOKIE_VERSION) return null;

  try {
    const iv = Buffer.from(parts[1], "base64url");
    const tag = Buffer.from(parts[2], "base64url");
    const ciphertext = Buffer.from(parts[3], "base64url");
    if (iv.length !== 12 || tag.length !== 16 || ciphertext.length > 2048) return null;
    const decipher = createDecipheriv("aes-256-gcm", encryptionKey(secret), iv);
    decipher.setAAD(Buffer.from(COOKIE_VERSION, "utf8"));
    decipher.setAuthTag(tag);
    const plaintext = Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString("utf8");
    const value: unknown = JSON.parse(plaintext);
    if (!isWorkspaceSession(value)) return null;
    const now = Math.floor(Date.now() / 1000);
    if (value.expiresAt <= now || value.expiresAt > now + SESSION_SECONDS) return null;
    return value;
  } catch {
    return null;
  }
}

function isWorkspaceSession(value: unknown): value is WorkspaceSession {
  if (typeof value !== "object" || value === null) return false;
  const session = value as Partial<WorkspaceSession>;
  return typeof session.apiKey === "string"
    && session.apiKey.length >= 16
    && session.apiKey.length <= 1024
    && typeof session.user_id === "string"
    && session.user_id.length > 0
    && session.user_id.length <= 128
    && typeof session.name === "string"
    && session.name.length > 0
    && session.name.length <= 128
    && typeof session.role === "string"
    && VALID_ROLES.has(session.role)
    && Number.isSafeInteger(session.expiresAt);
}

export function sessionCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict" as const,
    path: "/",
    maxAge: SESSION_SECONDS,
  };
}
