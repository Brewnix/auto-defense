import { Badge } from "@/components/ui/badge";
import { isBlockedStatus } from "@/lib/auth";

export function statusBadgeVariant(
  status: string,
): "default" | "secondary" | "outline" | "destructive" {
  if (isBlockedStatus(status)) {
    return "default";
  }
  if (status === "waiting_on_plane" || status === "applied_pending_ack") {
    return "secondary";
  }
  return "outline";
}

export function StatusBadge({
  status,
  label,
}: {
  status: string;
  label: string;
}) {
  return <Badge variant={statusBadgeVariant(status)}>{label}</Badge>;
}
