"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

export function TokenForm({ smokeAllowed }: { smokeAllowed: boolean }) {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [principal, setPrincipal] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setOk(false);
    try {
      const body: { token?: string; principal?: string } = {};
      if (token) {
        body.token = token;
      }
      if (smokeAllowed && principal.trim()) {
        body.principal = principal.trim();
      }
      const response = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = (await response.json()) as { error?: string };
      if (!response.ok) {
        setError(payload.error || "could not store session");
        return;
      }
      setOk(true);
      router.replace("/");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not store session");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save}>
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="ui-token">AIMMUNE_UI_TOKEN</FieldLabel>
          <Input
            id="ui-token"
            type="password"
            autoComplete="off"
            value={token}
            onChange={(event) => setToken(event.target.value)}
          />
          <FieldDescription>
            Loopback smoke / serve door. Authorization: Bearer on API routes, or
            this cookie after submit. Machine doors stay <code>hm_site_</code>.
          </FieldDescription>
        </Field>
        {smokeAllowed ? (
          <Field>
            <FieldLabel htmlFor="ui-principal">Smoke principal (loopback)</FieldLabel>
            <Input
              id="ui-principal"
              autoComplete="off"
              value={principal}
              onChange={(event) => setPrincipal(event.target.value)}
              placeholder="0x… (not SIWE)"
            />
            <FieldDescription>
              Non-prod / <code>AIMMUNE_UI_ALLOW_SMOKE_PRINCIPAL=1</code> only.
              Does not claim <code>source:siwe</code>. Production human path is
              Connect wallet → personal_sign.
            </FieldDescription>
          </Field>
        ) : null}
        <Button type="submit" disabled={busy || (!token && !(smokeAllowed && principal.trim()))}>
          {busy ? "Saving…" : "Store session"}
        </Button>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        {ok ? <p className="text-sm text-muted-foreground">Saved.</p> : null}
      </FieldGroup>
    </form>
  );
}
