import type { SiteObjectId } from "./types";
import { isSiteObjectId } from "./check";

export function configuredSiteId(): string {
  return (
    process.env.AIMMUNE_SITE_ID?.trim() ||
    process.env.SITE_ID?.trim() ||
    "net-tn-cottage"
  );
}

export function standingObject(siteId: string): SiteObjectId {
  const id = `site:${siteId}`;
  if (!isSiteObjectId(id)) {
    throw new Error(`invalid standing object for site_id=${siteId}`);
  }
  return id;
}

export function irObject(siteId: string): SiteObjectId {
  const id = `site:${siteId}:ir`;
  if (!isSiteObjectId(id)) {
    throw new Error(`invalid :ir object for site_id=${siteId}`);
  }
  return id;
}

/** :host is deferred. Always fail closed. */
export function hostObject(_siteId: string): never {
  throw new Error("site:{site_id}:host is deferred; fail closed");
}

export function parseSiteObject(id: string): SiteObjectId {
  if (!isSiteObjectId(id)) {
    throw new Error(`fail closed: ${id} is not site:id or site:id:ir`);
  }
  return id;
}
