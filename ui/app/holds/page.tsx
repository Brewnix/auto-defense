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

export const dynamic = "force-dynamic";

export default async function HoldsPage() {
  let error: string | null = null;
  let snap = null;
  try {
    snap = await loadSnapshot();
  } catch (err) {
    error = err instanceof Error ? err.message : "snapshot failed";
  }

  return (
    <AppShell siteId={snap?.site_id} planeReachable={snap?.plane_reachable}>
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load holds</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex flex-col gap-2">
        <h2 className="font-heading text-xl font-medium">Holds / tickets</h2>
        <p className="text-sm text-muted-foreground">
          Notify queue + auditor watches. Copy never says blocked from resolve
          alone. Local approve/deny is offered only when the plane is down or no
          ticket exists yet.
        </p>
      </div>
      {!snap?.holds.length ? (
        <EmptyState
          icon={TicketIcon}
          title="No holds"
          description="Propose/hold receipts enqueue here until drained or locally resolved."
        />
      ) : (
        <div className="flex flex-col gap-4">
          {snap.holds.map((hold) => (
            <Card key={hold.receipt_id}>
              <CardHeader>
                <CardTitle className="font-mono text-sm">{hold.receipt_id}</CardTitle>
                <CardDescription>
                  {hold.held?.tool || "held companion"}
                  {hold.held?.subject?.value
                    ? ` · ${hold.held.subject.kind}:${hold.held.subject.value}`
                    : ""}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={hold.status} label={hold.label} />
                  {hold.ticket_id ? (
                    <span className="text-xs text-muted-foreground">
                      ticket {hold.ticket_id}
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">no plane ticket</span>
                  )}
                  {hold.watch_status ? (
                    <span className="text-xs text-muted-foreground">
                      watch {hold.watch_status}
                    </span>
                  ) : null}
                </div>
                {hold.status === "waiting_on_plane" ? (
                  <Alert>
                    <AlertTitle>Waiting on plane</AlertTitle>
                    <AlertDescription>
                      An auditor ticket exists and the plane is reachable. Slice 2
                      poll applies intent. This console will not double-resolve.
                    </AlertDescription>
                  </Alert>
                ) : null}
                <HoldActions
                  receiptId={hold.receipt_id}
                  canLocal={Boolean(hold.can_local_resolve)}
                />
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </AppShell>
  );
}
