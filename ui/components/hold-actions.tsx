"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";

export function HoldActions({
  receiptId,
  canLocal,
  canExecute,
  canWrite,
}: {
  receiptId: string;
  canLocal: boolean;
  canExecute: boolean;
  canWrite: boolean;
}) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "deny" | "annotate" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const showResolve = canLocal && canExecute;
  const showAnnotate = canWrite;
  if (!showResolve && !showAnnotate) {
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
          note: canWrite && note.trim() ? note.trim() : undefined,
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

  async function annotateOnly() {
    if (!note.trim()) {
      setError("note required");
      return;
    }
    setBusy("annotate");
    setError(null);
    try {
      const response = await fetch("/api/annotate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          receipt_id: receiptId,
          note: note.trim(),
        }),
      });
      const payload = (await response.json()) as { error?: string };
      if (!response.ok) {
        setError(payload.error || "annotate failed");
        return;
      }
      setNote("");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "annotate failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <FieldGroup>
      {showAnnotate ? (
        <Field>
          <FieldLabel htmlFor={`note-${receiptId}`}>Optional note</FieldLabel>
          <Textarea
            id={`note-${receiptId}`}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            maxLength={500}
            rows={2}
            placeholder="Short redacted annotate (write on :ir)"
          />
          <FieldDescription>
            write without execute is annotate-only. Re-Check at act time.
          </FieldDescription>
        </Field>
      ) : (
        <FieldDescription>
          execute on :ir — note omitted (write not granted).
        </FieldDescription>
      )}
      <div className="flex flex-wrap gap-2">
        {showResolve ? (
          <>
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
          </>
        ) : null}
        {showAnnotate ? (
          <Button
            variant="secondary"
            onClick={annotateOnly}
            disabled={busy !== null}
          >
            {busy === "annotate" ? "Annotating…" : "Annotate only"}
          </Button>
        ) : null}
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </FieldGroup>
  );
}
