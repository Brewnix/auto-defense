import { FolderOpenIcon } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { IncidentClose } from "@/components/incident-close";
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
import { formatSubject } from "@/lib/incident";

export const dynamic = "force-dynamic";

export default async function IncidentsPage() {
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
          <AlertTitle>Could not load incidents</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex flex-col gap-2">
        <h2 className="font-heading text-xl font-medium">Incidents</h2>
        <p className="text-sm text-muted-foreground">
          fyber.incident/v0 overlay (security + ops). Side index only — contain
          is not gated on this store. Human close is refused while grant_active.
        </p>
      </div>
      {!snap?.incidents.length ? (
        <EmptyState
          icon={FolderOpenIcon}
          title="No incidents"
          description="Propose/hold/contain cycles open or join a security side-record. Health sell_pause prefers ops."
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>incident_id</TableHead>
              <TableHead>kind</TableHead>
              <TableHead>status</TableHead>
              <TableHead>severity</TableHead>
              <TableHead>summary</TableHead>
              <TableHead>subjects</TableHead>
              <TableHead>links</TableHead>
              <TableHead>receipts / tickets</TableHead>
              <TableHead>opened</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {snap.incidents.map((row) => (
              <TableRow key={row.incident_id}>
                <TableCell className="font-mono text-xs">{row.incident_id}</TableCell>
                <TableCell>
                  <Badge variant="outline">{row.kind}</Badge>
                </TableCell>
                <TableCell>
                  <Badge variant={row.status === "open" ? "default" : "secondary"}>
                    {row.status}
                  </Badge>
                </TableCell>
                <TableCell>{row.severity}</TableCell>
                <TableCell className="max-w-xs truncate text-xs">
                  {row.summary_redacted}
                </TableCell>
                <TableCell className="text-xs">
                  {(row.primary_subjects || []).map(formatSubject).join(", ")}
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {row.links?.opening_receipt_id || row.links?.opening_trace_id || "—"}
                </TableCell>
                <TableCell className="text-xs">
                  {row.index?.receipt_count ?? 0} / {row.index?.ticket_count ?? 0}
                </TableCell>
                <TableCell className="text-xs">{row.opened_at}</TableCell>
                <TableCell>
                  {row.status === "open" && row.incident_id ? (
                    <IncidentClose
                      incidentId={row.incident_id}
                      grantActive={Boolean(row.grant_active)}
                    />
                  ) : row.close_reason ? (
                    <span className="text-xs text-muted-foreground">{row.close_reason}</span>
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </AppShell>
  );
}
