import { ShieldAlertIcon } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { loadSnapshot } from "@/lib/aimmune";

export const dynamic = "force-dynamic";

export default async function OverviewPage() {
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
          <AlertTitle>Could not load site state</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {snap ? (
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle>Site</CardTitle>
              <CardDescription>Local source of truth</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="font-medium">{snap.site_id}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Plane</CardTitle>
              <CardDescription>AIMMUNE_PLANE_REACHABLE</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <Badge variant={snap.plane_reachable ? "default" : "outline"}>
                {snap.plane_reachable ? "reachable" : "down"}
              </Badge>
              <p className="text-sm text-muted-foreground">
                When a ticket exists and the plane is up, wait on plane poll. Do
                not double-resolve from this console.
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Sell state</CardTitle>
              <CardDescription>Best-effort; stale unknown is OK</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <div className="flex flex-wrap gap-2">
                <Badge variant="secondary">{snap.sell_state.value}</Badge>
                <Badge variant="outline">
                  {snap.sell_state.stale ? "stale" : "fresh"}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                Source: {snap.sell_state.source || "unknown"}
                {snap.sell_state.ts ? ` · ${snap.sell_state.ts}` : ""}
              </p>
            </CardContent>
          </Card>
        </div>
      ) : (
        <EmptyState
          icon={ShieldAlertIcon}
          title="No snapshot"
          description="Set AIMMUNE_STATE_DIR and AIMMUNE_UI_TOKEN, then reload."
        />
      )}
      <Alert>
        <AlertTitle>Read-mostly console</AlertTitle>
        <AlertDescription>
          Writes are local approve/deny of a held companion, plus optional grant
          propose / plane-down mint-local on /grants. No IR chat, no rule-pack
          editor, no SID UI. Ticket approve is not elevation.
        </AlertDescription>
      </Alert>
    </AppShell>
  );
}
