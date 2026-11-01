"use client";

import { FormEvent, useState } from "react";

export default function WorkspaceLogin() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (working) return;
    setWorking(true);
    setError(null);
    try {
      const response = await fetch("/api/workspace-session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
        cache: "no-store",
      });
      if (!response.ok) {
        const body: { detail?: string } = await response.json().catch(() => ({}));
        throw new Error(body.detail || "Could not sign in.");
      }
      window.location.assign("/workspace");
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "Could not sign in.");
      setPassword("");
    } finally {
      setWorking(false);
    }
  };
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-5 px-6">
      <h1 className="text-3xl font-semibold">RFQ workspace sign in</h1>
      <p className="text-sm text-[#52656b]">
        Enter the access password supplied by your workspace administrator.
        This single-operator gate is not a multi-tenant customer identity system.
      </p>
      <form onSubmit={(event) => { void submit(event); }} className="flex flex-col gap-4">
        <label htmlFor="workspace-password" className="text-sm font-medium">Workspace password</label>
        <input
          id="workspace-password" type="password" autoComplete="current-password"
          value={password} onChange={(event) => setPassword(event.target.value)}
          required minLength={1} className="rounded-lg border border-[#d6cbbd] p-3"
        />
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <button type="submit" disabled={working || !password} className="rfq-primary disabled:opacity-50">
          {working ? "Checking access…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
