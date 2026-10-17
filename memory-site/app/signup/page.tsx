import { redirect } from "next/navigation";
import { AuthForm } from "../components/AuthForm";
import { signedIn } from "../lib/session";
export const metadata = { title: "Create a workspace" };
export default async function Page() {
  if (await signedIn()) redirect("/dashboard");
  return <AuthForm signup />;
}
