import { NextRequest, NextResponse } from "next/server";
import {
  createWorkspaceSession,
  readWorkspaceSession,
  sessionCookieOptions,
  workspaceAuthStatus,
  WORKSPACE_COOKIE,
  type WorkspaceUser,
} from "@/lib/workspace-auth";

// Per-process throttle only. A public deployment still needs a shared edge limit.
const recentAttempts: number[] = [];
function allowAttempt(): boolean {
  const now = Date.now();
  while (recentAttempts.length && now - recentAttempts[0] >= 60_000) recentAttempts.shift();
  if (recentAttempts.length >= 10) return false;
  recentAttempts.push(now);
  return true;
}

async function readBoundedBody(request: NextRequest, limit: number): Promise<string | null> {
  const reader = request.body?.getReader();
  if (!reader) return "";
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > limit) {
        await reader.cancel();
        return null;
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(bytes);
}

function isWorkspaceUser(value: unknown): value is WorkspaceUser {
  if (typeof value !== "object" || value === null) return false;
  const user = value as Partial<WorkspaceUser>;
  return typeof user.user_id === "string" && user.user_id.length > 0
    && typeof user.name === "string" && user.name.length > 0
    && typeof user.role === "string" && ["admin", "reviewer", "viewer"].includes(user.role)
    && typeof user.workspace_id === "string" && /^[A-Za-z0-9][A-Za-z0-9._-]{1,62}$/.test(user.workspace_id);
}

export async function GET(request: NextRequest) {
  const cookie = request.cookies.get(WORKSPACE_COOKIE)?.value;
  const status = workspaceAuthStatus(cookie);
  if (status === "misconfigured") {
    return NextResponse.json({ detail: "Per-user workspace authentication is not configured." }, { status: 503 });
  }
  const session = cookie ? readWorkspaceSession(cookie) : null;
  return NextResponse.json(
    { authenticated: status === "open" || status === "authenticated", configured: status !== "open", user: session ? { user_id: session.user_id, name: session.name, role: session.role, workspace_id: session.workspace_id } : null },
    { status: 200, headers: { "Cache-Control": "no-store" } },
  );
}

export async function POST(request: NextRequest) {
  const status = workspaceAuthStatus(request.cookies.get(WORKSPACE_COOKIE)?.value);
  if (status === "misconfigured") {
    return NextResponse.json({ detail: "Per-user workspace authentication is not configured." }, { status: 503 });
  }
  if (status === "open") return NextResponse.json({ authenticated: true, user: null });
  if (!allowAttempt()) {
    return NextResponse.json(
      { detail: "Too many sign-in attempts. Try again later." },
      { status: 429, headers: { "Retry-After": "60" } },
    );
  }
  const contentLength = Number(request.headers.get("content-length") || "0");
  if (contentLength > 4096) return NextResponse.json({ detail: "Invalid sign-in request." }, { status: 413 });
  const rawBody = await readBoundedBody(request, 4096);
  if (rawBody === null) return NextResponse.json({ detail: "Invalid sign-in request." }, { status: 413 });
  const body: unknown = await Promise.resolve().then(() => JSON.parse(rawBody)).catch(() => null);
  const apiKey = typeof body === "object" && body !== null && "apiKey" in body
    ? (body as { apiKey: unknown }).apiKey : undefined;
  if (typeof apiKey !== "string" || apiKey.length < 16 || apiKey.length > 1024) {
    return NextResponse.json({ detail: "Invalid access key." }, { status: 401 });
  }

  const upstream = (process.env.RFQ_ASSISTANT_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  let user: WorkspaceUser;
  try {
    const response = await fetch(`${upstream}/api/session`, {
      method: "GET",
      headers: { "X-API-Key": apiKey, accept: "application/json" },
      cache: "no-store",
      redirect: "manual",
    });
    if (response.status === 401 || response.status === 403) {
      return NextResponse.json({ detail: "Invalid access key." }, { status: 401 });
    }
    if (!response.ok) {
      return NextResponse.json({ detail: "Workspace authentication is unavailable." }, { status: 503 });
    }
    const profile: unknown = await response.json();
    if (!isWorkspaceUser(profile)) {
      return NextResponse.json({ detail: "Workspace authentication is unavailable." }, { status: 503 });
    }
    user = profile;
  } catch {
    return NextResponse.json({ detail: "Workspace authentication is unavailable." }, { status: 503 });
  }

  const token = createWorkspaceSession(apiKey, user);
  if (!token) return NextResponse.json({ detail: "Workspace authentication is unavailable." }, { status: 503 });
  const response = NextResponse.json(
    { authenticated: true, user },
    { headers: { "Cache-Control": "no-store" } },
  );
  response.cookies.set(WORKSPACE_COOKIE, token, sessionCookieOptions());
  return response;
}

export async function DELETE() {
  const response = NextResponse.json({ authenticated: false }, { headers: { "Cache-Control": "no-store" } });
  response.cookies.set(WORKSPACE_COOKIE, "", { ...sessionCookieOptions(), maxAge: 0 });
  return response;
}
