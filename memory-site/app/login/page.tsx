import { redirect } from "next/navigation";
import { AuthForm } from "../components/AuthForm";
import { signedIn } from "../lib/session";
export const metadata = { title: "Sign in" };
export default async function Login() {
  if (await signedIn()) redirect("/dashboard");
  return <AuthForm />;
}
