"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export function GrantPropose({ planeReachable }: { planeReachable?: boolean }) {
  const router = useRouter();
  const [incidentId, setIncidentId] = useState("");
  const [profile, setProfile] = useState(planeReachable ? "ir_elevated" : "break_glass");
  const [ttl, setTtl] = useState(planeReachable ? "14400" : "1800");
  const [reason, setReason] = useState("");
  const [tools, setTools] = useState("health.restart_service,notify.operator");
  const [ticketId, setTicketId] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setOk(null);
    try {
      const action = planeReachable ? "propose" : "mint-local";
      const response = await fetch("/api/grant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          incident_id: incidentId,
          profile,
          ttl: Number(ttl) || 1800,
          reason,
          tools: tools.split(",").map((part) => part.trim()).filter(Boolean),
          ticket_id: ticketId,
          notes,
        }),
      });
      const payload = (await response.json()) as { error?: string; grant_id?: string };
      if (!response.ok) {
        setError(payload.error || "grant failed");
        return;
      }
      setOk(payload.grant_id || "submitted");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "grant failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="grant-incident">incident_id</FieldLabel>
          <Input
            id="grant-incident"
            value={incidentId}
            onChange={(event) => setIncidentId(event.target.value)}
            required
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="grant-profile">rails_profile</FieldLabel>
          <Input
            id="grant-profile"
            value={profile}
            onChange={(event) => setProfile(event.target.value)}
          />
          <FieldDescription>ir_elevated or break_glass. Strict is not an elevation.</FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="grant-ttl">ttl_s</FieldLabel>
          <Input
            id="grant-ttl"
            type="number"
            value={ttl}
            onChange={(event) => setTtl(event.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="grant-tools">tools (comma)</FieldLabel>
          <Input
            id="grant-tools"
            value={tools}
            onChange={(event) => setTools(event.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="grant-reason">reason_redacted</FieldLabel>
          <Textarea
            id="grant-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            required
          />
          <FieldDescription>No prompts or payloads.</FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="grant-ticket">ticket_id (or local stub)</FieldLabel>
          <Input
            id="grant-ticket"
            value={ticketId}
            onChange={(event) => setTicketId(event.target.value)}
          />
        </Field>
        {!planeReachable ? (
          <Field>
            <FieldLabel htmlFor="grant-notes">notes (required for local mint)</FieldLabel>
            <Textarea
              id="grant-notes"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              required
            />
          </Field>
        ) : null}
        <Button type="submit" disabled={busy || !incidentId || !reason}>
          {busy
            ? "Submitting…"
            : planeReachable
              ? "Propose to plane"
              : "Mint local (plane down)"}
        </Button>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        {ok ? <p className="text-sm text-muted-foreground">grant {ok}</p> : null}
      </FieldGroup>
    </form>
  );
}
