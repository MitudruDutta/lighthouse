import "server-only";
import { cache } from "react";
import { cookies } from "next/headers";
import { DESK_COOKIE, desk } from "./api";
export async function operationsToken() {
  return (await cookies()).get(DESK_COOKIE)?.value;
}
export const operations = cache(async function operations<T>(
  path: string,
): Promise<T | null> {
  const token = await operationsToken();
  if (!token) return null;
  const response = await desk<T>(`/api/operations/${path}`, token);
  return response.ok ? response.data : null;
});
