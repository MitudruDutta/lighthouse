import "server-only";
import { cookies } from "next/headers";
import { COOKIE, request } from "./server";

// The signed-in person, or null: the session is checked with the API, so an expired one
// counts as signed out.
export async function signedIn(): Promise<{ name: string } | null> {
  const token = (await cookies()).get(COOKIE)?.value;
  if (!token) return null;
  const { status, data } = await request("/console/overview", token);
  return status === 200 ? data.user : null;
}
