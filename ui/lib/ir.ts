import { cookies, headers } from "next/headers";

import {
  COOKIE_NAME,
  PRINCIPAL_COOKIE,
  PRINCIPAL_HEADER,
  configuredUiToken,
  resolvePrincipal,
  tokensEqual,
} from "@/lib/auth";
import { readSiweSession } from "@/lib/siwe/session";
import { checkIrAct, irCaps, type IrAct, type IrCaps } from "@/lib/sociacl-light/gate";
import { configuredSiteId } from "@/lib/sociacl-light/objects";
import { ownerPrincipalsFromEnv } from "@/lib/sociacl-light/principal";
import { getProcessAcl } from "@/lib/sociacl-light/store";
import type { AccessorId, CheckResult } from "@/lib/sociacl-light/types";

export type IrSession = {
  principal: AccessorId | null;
  source: "siwe" | "smoke" | null;
  exp: number | null;
  siteId: string;
  caps: IrCaps;
  now: number;
};

export async function loadIrSession(): Promise<IrSession> {
  const jar = await cookies();
  const hdrs = await headers();
  const expected = configuredUiToken();
  const provided = jar.get(COOKIE_NAME)?.value || null;
  const tokenOk = Boolean(expected && tokensEqual(provided, expected));
  const principalCookie = jar.get(PRINCIPAL_COOKIE)?.value || null;
  const now = Math.floor(Date.now() / 1000);
  const { principal, source } = resolvePrincipal({
    cookie: principalCookie,
    header: hdrs.get(PRINCIPAL_HEADER),
    tokenOk,
  });
  const siteId = configuredSiteId();
  const owners = ownerPrincipalsFromEnv();
  const acl = getProcessAcl(siteId);
  const siwe = source === "siwe" ? readSiweSession(principalCookie, undefined, now) : null;
  return {
    principal,
    source,
    exp: siwe?.exp ?? null,
    siteId,
    now,
    caps: irCaps(acl, siteId, principal, now, owners),
  };
}

export async function requireIrAct(act: IrAct): Promise<
  { ok: true; session: IrSession } | { ok: false; status: number; error: string; check: CheckResult }
> {
  const session = await loadIrSession();
  if (!session.principal) {
    return {
      ok: false,
      status: 403,
      error: "principal required (SIWE / cottage session, or AIMMUNE_UI_SMOKE_PRINCIPAL on loopback)",
      check: { allowed: false, reason: "principal required" },
    };
  }
  const check = checkIrAct(
    getProcessAcl(session.siteId),
    session.siteId,
    session.principal,
    act,
    session.now,
    ownerPrincipalsFromEnv(),
  );
  if (!check.allowed) {
    return { ok: false, status: 403, error: check.reason, check };
  }
  return { ok: true, session };
}
