import type { AccessorId } from "./types";

const ETH = /^0x[a-fA-F0-9]{40}$/;

/** Cottage SIWE address when it looks like one; otherwise a case-folded id. */
export function normalizePrincipal(raw: string | null | undefined): AccessorId | null {
  if (!raw) {
    return null;
  }
  const trimmed = raw.trim();
  if (!trimmed) {
    return null;
  }
  if (ETH.test(trimmed)) {
    return trimmed.toLowerCase();
  }
  return trimmed.toLowerCase();
}

export function ownerPrincipalsFromEnv(
  raw: string | null | undefined = process.env.AIMMUNE_OWNER_PRINCIPALS,
): AccessorId[] {
  if (!raw) {
    return [];
  }
  const out: AccessorId[] = [];
  for (const part of raw.split(",")) {
    const id = normalizePrincipal(part);
    if (id && !out.includes(id)) {
      out.push(id);
    }
  }
  return out;
}

export function isOwnerPrincipal(
  principal: AccessorId | null | undefined,
  owners: readonly AccessorId[] = ownerPrincipalsFromEnv(),
): boolean {
  if (!principal) {
    return false;
  }
  return owners.includes(principal);
}

export function smokePrincipalFromEnv(): AccessorId | null {
  return normalizePrincipal(process.env.AIMMUNE_UI_SMOKE_PRINCIPAL);
}
