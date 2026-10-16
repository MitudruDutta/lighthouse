import Link from "next/link";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { COOKIE, DOCS, request } from "@/app/lib/server";
import { Console } from "@/app/components/Console";
export const metadata = { title: "Developer console" };
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ section?: string[] }>;
  searchParams: Promise<{ project?: string }>;
}) {
  const { section } = await params;
  const view = section?.[0] ?? "overview";
  if (view === "billing") redirect("/dashboard/usage");
  if (
    (section && section.length > 1) ||
    ![
      "overview",
      "projects",
      "keys",
      "memory",
      "usage",
      "settings",
      "connect",
    ].includes(view)
  )
    notFound();
  const token = (await cookies()).get(COOKIE)?.value;
  if (!token) redirect("/login");
  const response = await request("/console/overview", token);
  if (response.status === 401) redirect("/login");
  if (response.status !== 200)
    return (
      <main id="main" className="unavailable">
        <h1>Your workspace is temporarily unavailable.</h1>
        <p>Please try again shortly. Your account and memories are saved.</p>
        <Link href="/dashboard">Try again</Link>
      </main>
    );
  const project = (await searchParams).project;
  return (
    <Console
      initial={response.data}
      view={view}
      requestedProject={project}
      docs={DOCS}
      publicApi={process.env.MEMORY_PUBLIC_API ?? "http://localhost:8200"}
    />
  );
}
