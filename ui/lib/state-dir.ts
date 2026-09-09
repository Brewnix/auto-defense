import path from "node:path";

/**
 * Same resolution the UI already uses for `python -m aimmune --state-dir`.
 * Prefer AIMMUNE_STATE_DIR; accept the historical AIMIMUNE_STATE_DIR typo.
 * No implicit /var/lib/aimmune default — other UI routes only pass the env
 * when it is set.
 */
export function configuredStateDir(): string | null {
  const env =
    process.env.AIMMUNE_STATE_DIR?.trim() ||
    process.env.AIMIMUNE_STATE_DIR?.trim();
  return env || null;
}

export function sociaclMockStorePath(): string | null {
  const dir = configuredStateDir();
  if (!dir) {
    return null;
  }
  return path.join(dir, "sociacl-mock.json");
}
