import { NextRequest, NextResponse } from "next/server";
import {
  issueSession, sessionCookieOptions, verifyWorkspacePassword,
  workspaceAuthStatus, WORKSPACE_COOKIE,
} from "@/lib/workspace-auth";

// Single-instance local credential throttle. A real public deployment also
// needs a shared edge login limit and separate per-user identity.
const recentAttempts: number[] = [];
function allowAttempt(): boolean {
  const now = Date.now();
  while (recentAttempts.length && now - recentAttempts[0] >= 60_000) recentAttempts.shift();
  if (recentAttempts.length >= 10) return false;
  recentAttempts.push(now);
  return true;
}

export async function GET(request: NextRequest) {
  const status = workspaceAuthStatus(request.cookies.get(WORKSPACE_COOKIE)?.value);
  return NextResponse.json(
    { authenticated: status === "open" || status === "authenticated", configured: status !== "misconfigured" },
    { status: status === "misconfigured" ? 503 : 200, headers: { "Cache-Control": "no-store" } },
  );
}

export async function POST(request: NextRequest) {
  const status = workspaceAuthStatus(request.cookies.get(WORKSPACE_COOKIE)?.value);
  if (status === "misconfigured") {
    return NextResponse.json({ detail: "Workspace login is not configured." }, { status: 503 });
  }
  if (status === "open") return NextResponse.json({ authenticated: true });
  if (!allowAttempt()) {
    return NextResponse.json(
      { detail: "Too many login attempts. Try again later." },
      { status: 429, headers: { "Retry-After": "60" } },
    );
  }
  const length = Number(request.headers.get("content-length") || "0");
  if (length > 4096) return NextResponse.json({ detail: "Invalid login request." }, { status: 413 });
  const body: unknown = await request.json().catch(() => null);
  const password = typeof body === "object" && body !== null && "password" in body
    ? (body as { password: unknown }).password : undefined;
  if (typeof password !== "string" || !verifyWorkspacePassword(password)) {
    return NextResponse.json({ detail: "Invalid workspace password." }, { status: 401 });
  }
  const token = issueSession();
  if (!token) return NextResponse.json({ detail: "Workspace login is unavailable." }, { status: 503 });
  const response = NextResponse.json({ authenticated: true }, { headers: { "Cache-Control": "no-store" } });
  response.cookies.set(WORKSPACE_COOKIE, token, sessionCookieOptions());
  return response;
}

export async function DELETE() {
  const response = NextResponse.json({ authenticated: false }, { headers: { "Cache-Control": "no-store" } });
  response.cookies.set(WORKSPACE_COOKIE, "", { ...sessionCookieOptions(), maxAge: 0 });
  return response;
}
