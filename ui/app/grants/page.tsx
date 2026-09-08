import { KeyRoundIcon } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { GrantPropose } from "@/components/grant-propose";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { loadSnapshot } from "@/lib/aimmune";
import { loadIrSession } from "@/lib/ir";

export const dynamic = "force-dynamic";

export default async function GrantsPage() {
  const session = await loadIrSession();
  let error: string | null = null;
  let snap = null;
  try {
    snap = await loadSnapshot();
  } catch (err) {
    error = err instanceof Error ? err.message : "snapshot failed";
  }

  return (
    <AppShell
      siteId={snap?.site_id}
      planeReachable={snap?.plane_reachable}
      principal={session.principal}
    >
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load grants</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex flex-col gap-2">
        <h2 className="font-heading text-xl font-medium">Privilege grants</h2>
        <p className="text-sm text-muted-foreground">
          Time-bounded policy elevation for one incident. Ticket approved is not
          an elevation. Grant approved is not a firewall apply. Resolve/revoke
          stay on the plane. Human propose / mint-local re-Check{" "}
          <code>execute</code> on <code>{session.caps.object}</code>;{" "}
          <code>break_glass</code> also requires an owner principal.
        </p>
      </div>
      <Alert>
        <AlertTitle>Ticket ≠ grant ≠ apply</AlertTitle>
        <AlertDescription>
          An auditor ticket approve does not mint rails. An approved grant does
          not apply a block. Site never POSTs /resolve or /revoke. Plane #50
          propose when up; home mint-local when the plane is down (GrantStore).
        </AlertDescription>
      </Alert>
      <GrantPropose
        planeReachable={snap?.plane_reachable}
        canMint={session.caps.execute}
        canBreakGlass={session.caps.break_glass}
      />
      {!snap?.grants?.length ? (
        <EmptyState
          icon={KeyRoundIcon}
          title="No grants in the site cache"
          description="Propose on the plane when reachable, or mint-local while the plane is down (open incident + ticket + notes)."
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>grant_id</TableHead>
              <TableHead>incident</TableHead>
              <TableHead>status</TableHead>
              <TableHead>profile</TableHead>
              <TableHead>active_until</TableHead>
              <TableHead>asks</TableHead>
              <TableHead>ticket</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {snap.grants.map((row) => (
              <TableRow key={row.grant_id || row.trace_id}>
                <TableCell className="font-mono text-xs">{row.grant_id}</TableCell>
                <TableCell className="font-mono text-xs">{row.incident_id}</TableCell>
                <TableCell>
                  <Badge variant={row.status === "approved" ? "default" : "secondary"}>
                    {row.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-xs">
                  {row.rails_profile || row.rails_profile_requested || "—"}
                </TableCell>
                <TableCell className="text-xs">{row.active_until || "—"}</TableCell>
                <TableCell className="text-xs">
                  {(row.asks || []).map((ask) => ask.kind).filter(Boolean).join(", ")}
                </TableCell>
                <TableCell className="font-mono text-xs">{row.ticket_id || "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </AppShell>
  );
}
