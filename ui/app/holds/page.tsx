import { TicketIcon } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { HoldActions } from "@/components/hold-actions";
import { StatusBadge } from "@/components/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { loadSnapshot } from "@/lib/aimmune";
import { loadIrSession } from "@/lib/ir";
import { redactHold } from "@/lib/redact";

export const dynamic = "force-dynamic";

export default async function HoldsPage() {
  const session = await loadIrSession();
  let error: string | null = null;
  let snap = null;
  try {
    snap = await loadSnapshot();
  } catch (err) {
    error = err instanceof Error ? err.message : "snapshot failed";
  }

  const holds = (snap?.holds || []).map((hold) =>
    session.caps.read ? hold : redactHold(hold),
  );

  return (
    <AppShell
      siteId={snap?.site_id}
      planeReachable={snap?.plane_reachable}
      principal={session.principal}
    >
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load holds</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex flex-col gap-2">
        <h2 className="font-heading text-xl font-medium">Holds / tickets</h2>
        <p className="text-sm text-muted-foreground">
          Local approve/deny re-Checks <code>execute</code> on{" "}
          <code>{session.caps.object}</code> at act time. Annotate is{" "}
          <code>write</code> only. see/read for the redacted view.
        </p>
      </div>
      {!session.caps.read ? (
        <Alert>
          <AlertTitle>Redacted view</AlertTitle>
          <AlertDescription>
            Check <code>see</code>/<code>read</code> on :ir is required to view
            hold subjects. Dual auth: UI token for loopback; principal for Check.
          </AlertDescription>
        </Alert>
      ) : null}
      {!holds.length ? (
        <EmptyState
          icon={TicketIcon}
          title="No holds"
          description="Propose/hold receipts enqueue here until drained or locally resolved."
        />
      ) : (
        <div className="flex flex-col gap-4">
          {holds.map((hold) => (
            <Card key={hold.receipt_id}>
              <CardHeader>
                <CardTitle className="font-mono text-sm">{hold.receipt_id}</CardTitle>
                <CardDescription>
                  {session.caps.read
                    ? `${hold.held?.tool || "held companion"}${
                        hold.held?.subject?.value
                          ? ` · ${hold.held.subject.kind}:${hold.held.subject.value}`
                          : ""
                      }`
                    : "redacted"}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={hold.status} label={hold.label} />
                  {session.caps.read && hold.ticket_id ? (
                    <span className="text-xs text-muted-foreground">
                      ticket {hold.ticket_id}
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      {session.caps.read ? "no plane ticket" : "redacted"}
                    </span>
                  )}
                </div>
                {hold.status === "waiting_on_plane" ? (
                  <Alert>
                    <AlertTitle>Waiting on plane</AlertTitle>
                    <AlertDescription>
                      An auditor ticket exists and the plane is reachable. Slice 2
                      poll applies intent. This console will not double-resolve.
                      Plane <code>POST …/resolve</code> remains JWT — out of slice 8.
                    </AlertDescription>
                  </Alert>
                ) : null}
                <HoldActions
                  receiptId={hold.receipt_id}
                  canLocal={Boolean(hold.can_local_resolve)}
                  canExecute={session.caps.execute}
                  canWrite={session.caps.write}
                />
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </AppShell>
  );
}
