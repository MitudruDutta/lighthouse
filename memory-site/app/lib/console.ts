// The console's requests go through this site's server, which adds the session.
export async function call(path: string, method = "GET", body?: unknown) {
  const response = await fetch("/api/console" + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail ?? "Please try again shortly.");
  return data;
}
