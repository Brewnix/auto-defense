import type { IncidentSubject } from "@/lib/types";

export function formatSubject(subject: IncidentSubject): string {
  if (subject.kind === "node_unit") {
    return `node_unit:${subject.node || "?"}/${subject.unit || "?"}`;
  }
  if (subject.kind === "health_class") {
    return `health_class:${subject.value || "?"}`;
  }
  if (subject.kind && subject.value) {
    return `${subject.kind}:${subject.value}`;
  }
  return subject.kind || subject.value || "?";
}
