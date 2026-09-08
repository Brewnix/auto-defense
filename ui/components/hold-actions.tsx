"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";

export function HoldActions({
  receiptId,
  canLocal,
}: {
  receiptId: string;
  canLocal: boolean;
}) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "deny" | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!canLocal) {
    return null;
  }

  async function act(action: "approve" | "deny") {
    setBusy(action);
    setError(null);
    try {
      const response = await fetch("/api/owner", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          receipt_id: receiptId,
          action,
          note: note.trim() || undefined,
        }),
      });
      const payload = (await response.json()) as { error?: string };
      if (!response.ok) {
        setError(payload.error || "resolve failed");
        return;
      }
      setNote("");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "resolve failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <FieldGroup>
      <Field>
        <FieldLabel htmlFor={`note-${receiptId}`}>Optional note</FieldLabel>
        <Textarea
          id={`note-${receiptId}`}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={500}
          rows={2}
          placeholder="Short redacted annotate (optional)"
        />
        <FieldDescription>Local approve/deny only. No plane resolve.</FieldDescription>
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => act("approve")} disabled={busy !== null}>
          {busy === "approve" ? "Approving…" : "Approve locally"}
        </Button>
        <Button
          variant="outline"
          onClick={() => act("deny")}
          disabled={busy !== null}
        >
          {busy === "deny" ? "Denying…" : "Deny locally"}
        </Button>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </FieldGroup>
  );
}
