"use server";
import { revalidatePath } from "next/cache";
import { desk } from "@/app/lib/api";
import { operationsToken } from "@/app/lib/operations-server";
export async function saveProfile(
  _: { error?: string; saved?: string },
  form: FormData,
): Promise<{ error?: string; saved?: string }> {
  const token = await operationsToken();
  if (!token) return { error: "Sign in to save your preferences." };
  let ports: unknown, vessels: unknown;
  try {
    ports = JSON.parse(String(form.get("ports") ?? "[]"));
    vessels = JSON.parse(String(form.get("vessels") ?? "[]"));
  } catch {
    return { error: "Please check your watchlist." };
  }
  const result = await desk(
    "/api/operations/profile",
    token,
    {
      name: String(form.get("name") ?? ""),
      timezone: String(form.get("timezone") ?? "UTC"),
      focus: String(form.get("focus") ?? "all"),
      view: String(form.get("view") ?? "attention"),
      ports,
      vessels,
    },
    "PUT",
  );
  if (!result.ok)
    return {
      error:
        result.status === 422
          ? "Check your name, timezone, and selected ports or vessels."
          : "Your preferences could not be saved. Please try again.",
    };
  revalidatePath("/profile");
  revalidatePath("/dashboard");
  revalidatePath("/desk");
  return { saved: "Your workspace preferences are saved." };
}

/** Follows or unfollows at once: the saved profile with this watchlist, and the rest
 * of the profile as it was saved, not as the form holds it now. */
export async function saveWatchlist(
  ports: string[],
  vessels: string[],
): Promise<{ error?: string; saved?: string }> {
  const token = await operationsToken();
  if (!token) return { error: "Sign in to follow ports and vessels." };
  const current = await desk<Record<string, unknown>>("/api/operations/profile", token);
  if (!current.ok) return { error: "Your watchlist could not be saved. Please try again." };
  const result = await desk(
    "/api/operations/profile",
    token,
    { ...current.data, ports, vessels },
    "PUT",
  );
  if (!result.ok)
    return {
      error:
        result.status === 422
          ? "Choose a port or vessel from the list."
          : "Your watchlist could not be saved. Please try again.",
    };
  revalidatePath("/profile");
  revalidatePath("/dashboard");
  revalidatePath("/desk");
  return { saved: "Watchlist saved." };
}
