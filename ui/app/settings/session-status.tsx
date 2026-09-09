"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup } from "@/components/ui/field";

function formatExp(exp: number | null): string {
  if (exp === null) {
    return "none (legacy v1 cookie)";
  }
  return new Date(exp * 1000).toISOString();
}

export function SessionStatus({
  source,
  principal,
  exp,
}: {
  source: "siwe" | "smoke" | null;
  principal: string | null;
  exp: number | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signOut() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/session", { method: "DELETE" });
      const payload = (await response.json()) as { error?: string };
      if (!response.ok) {
        setError(payload.error || "could not sign out");
        return;
      }
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not sign out");
    } finally {
      setBusy(false);
    }
  }

  return (
    <FieldGroup>
      <Field>
        <FieldDescription>
          Source <code>{source || "none"}</code>
          {principal ? (
            <>
              {" "}
              · principal <code className="font-mono">{principal}</code>
            </>
          ) : null}
          {source === "siwe" ? (
            <>
              {" "}
              · expires {formatExp(exp)}
            </>
          ) : null}
        </FieldDescription>
      </Field>
      <Button type="button" variant="outline" onClick={signOut} disabled={busy}>
        {busy ? "Signing out…" : "Sign out"}
      </Button>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </FieldGroup>
  );
}
