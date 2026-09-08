import { configuredSiteId } from "@/lib/sociacl-light/objects";

export const NONCE_COOKIE = "aimmune_siwe_nonce";
export const NONCE_TTL_MS = 10 * 60 * 1000;
export const SIWE_VERSION = "1";

/** RFC 3986 authority. Loopback is the cottage default. */
export function siweDomain(): string {
  return process.env.AIMMUNE_SIWE_DOMAIN?.trim() || "127.0.0.1";
}

export function siweUri(): string {
  const env = process.env.AIMMUNE_SIWE_URI?.trim();
  if (env) {
    return env;
  }
  const domain = siweDomain();
  const port = process.env.AIMMUNE_UI_PORT?.trim() || "3000";
  const host = domain.includes(":") ? domain : `${domain}:${port}`;
  return `http://${host}`;
}

/** Statement must bind site:{SITE_ID}. Custom text still has to include that token. */
export function siweStatement(siteId: string = configuredSiteId()): string {
  const env = process.env.AIMMUNE_SIWE_STATEMENT?.trim();
  if (env) {
    return env;
  }
  return `Sign in to AImmune site:${siteId}`;
}

export function siteBindToken(siteId: string = configuredSiteId()): string {
  return `site:${siteId}`;
}

/** Optional. When unset the client still sends chainId 1; the server accepts any. */
export function siweChainId(): number | undefined {
  const raw = process.env.AIMMUNE_SIWE_CHAIN_ID?.trim();
  if (!raw) {
    return undefined;
  }
  const n = Number(raw);
  if (!Number.isInteger(n) || n <= 0) {
    return undefined;
  }
  return n;
}

export function defaultClientChainId(): number {
  return siweChainId() ?? 1;
}
