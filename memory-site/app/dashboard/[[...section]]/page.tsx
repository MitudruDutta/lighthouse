import Link from "next/link";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { COOKIE, DOCS, request } from "@/app/lib/server";
import { Console } from "@/app/components/Console";
import "@/app/console.css";
export const metadata = { title: "Developer console" };
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ section?: string[] }>;
  searchParams: Promise<{ project?: string; workspace?: string; tab?: string }>;
}) {
  const { section } = await params;
  const view = section?.[0] ?? "overview";
  const query = await searchParams;
  // Earlier addresses of two pages.
  const moved: Record<string, string> = { billing: "plan", connect: "agents" };
  if (moved[view])
    redirect(`/dashboard/${moved[view]}${query.project ? `?project=${query.project}` : ""}`);
  if (
    (section && section.length > 1) ||
    ![
      "overview",
      "projects",
      "memory",
      "agents",
      "keys",
      "usage",
      "plan",
      "settings",
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
  return (
    <Console
      initial={response.data}
      view={view}
      requestedProject={query.project}
      requestedWorkspace={query.workspace}
      tab={query.tab}
      docs={DOCS}
      publicApi={process.env.MEMORY_PUBLIC_API ?? "http://localhost:8200"}
    />
  );
}
