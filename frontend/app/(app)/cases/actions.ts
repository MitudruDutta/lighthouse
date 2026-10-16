"use server";
import { revalidatePath } from "next/cache";
import { desk } from "@/app/lib/api";
import { caseHref } from "@/app/lib/operations";
import { operationsToken } from "@/app/lib/operations-server";
export type DecisionState = { error?: string; saved?: string };
export async function updateCase(
  _: DecisionState,
  form: FormData,
): Promise<DecisionState> {
  const token = await operationsToken();
  if (!token) return { error: "Sign in to make a decision." };
  const id = String(form.get("id") ?? "");
  const revision = Number(form.get("revision"));
  const operation = String(form.get("operation"));
  const text = String(form.get("text") ?? "");
  if (
    !id ||
    id.length > 200 ||
    !Number.isInteger(revision) ||
    text.length > 2000
  )
    return { error: "Please check the information you entered." };
  const result = await desk("/api/operations/case", token, {
    id,
    revision,
    operation,
    text,
  });
  if (!result.ok)
    return {
      error:
        result.status === 409
          ? "This case changed. Refresh and review its latest state."
          : result.status === 403
            ? "Take ownership first. Cases owned by a teammate stay with them."
            : result.status === 422
              ? "Add a short next step or outcome before saving."
              : "Your decision could not be saved. Please try again.",
    };
  revalidatePath(caseHref(id));
  revalidatePath("/dashboard");
  revalidatePath("/desk");
  return { saved: "Decision saved." };
}
