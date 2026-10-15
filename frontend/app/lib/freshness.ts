/** API timestamps without a zone are UTC. */
export function utcTime(at: string): number {
  return Date.parse(/T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(at) ? `${at}Z` : at);
}

export function isFresh(at: string | null | undefined, now: string, minutes: number): boolean {
  if (!at) return false;
  const age = utcTime(now) - utcTime(at);
  return Number.isFinite(age) && age >= -60_000 && age < minutes * 60_000;
}

export const ACCEPTED_WRITES = new Set(["created", "changed", "inserted", "unchanged"]);

export function failedSince(error?: { at: string } | null, success?: { at: string } | null): boolean {
  return Boolean(error && (!success || utcTime(error.at) > utcTime(success.at)));
}

export function rejectedWrites(receipts: Record<string, number> = {}): number {
  return Object.entries(receipts).reduce((sum, [status, count]) => sum + (ACCEPTED_WRITES.has(status) ? 0 : count), 0);
}
