"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

export default function WorkspaceLogin() {
  const router = useRouter();
  const [apiKey, setApiKey] = useState("");
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
        body: JSON.stringify({ apiKey }),
        cache: "no-store",
      });
      if (!response.ok) {
        const body: { detail?: string } = await response.json().catch(() => ({}));
        throw new Error(body.detail || "Could not sign in.");
      }
      setApiKey("");
      router.replace("/workspace");
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "Could not sign in.");
      setApiKey("");
    } finally {
      setWorking(false);
    }
  };
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-5 px-6">
      <h1 className="text-3xl font-semibold">RFQ workspace sign in</h1>
      <p className="text-sm text-[#52656b]">
        Use your personal workspace access key. Your role controls which actions are available.
        This deployment remains a single workspace and does not isolate multiple distributor organizations.
      </p>
      <form onSubmit={(event) => { void submit(event); }} className="flex flex-col gap-4">
        <label htmlFor="workspace-access-key" className="text-sm font-medium">Personal access key</label>
        <input
          id="workspace-access-key" type="password" autoComplete="current-password"
          value={apiKey} onChange={(event) => setApiKey(event.target.value)}
          required minLength={16} maxLength={1024} className="rounded-lg border border-[#d6cbbd] p-3"
        />
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <button type="submit" disabled={working || apiKey.length < 16} className="rfq-primary disabled:opacity-50">
          {working ? "Checking access…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
