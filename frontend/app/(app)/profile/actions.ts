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
