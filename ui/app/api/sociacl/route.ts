import { NextResponse } from "next/server";

import { loadIrSession } from "@/lib/ir";
import { listLiveSiteGrants } from "@/lib/sociacl-light/store";

export async function GET() {
  const session = await loadIrSession();
  if (!session.principal) {
    return NextResponse.json(
      { error: "principal required (SIWE / cottage session)" },
      { status: 403 },
    );
  }
  return NextResponse.json({
    ok: true,
    principal: session.principal,
    source: session.source,
    site_id: session.siteId,
    grants: listLiveSiteGrants(session.siteId, session.now),
  });
}
