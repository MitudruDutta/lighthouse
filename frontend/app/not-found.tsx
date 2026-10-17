import Link from "next/link";

export default function NotFound() {
  return (
    <main id="main" className="mx-auto max-w-xl px-5 py-20">
      <h1 className="serif text-3xl">Nothing here by that name</h1>
      <p className="mt-3 text-muted">
        The graph has no such port, berth, ship, port call, or episode. It may have a key of another form: find it by
        its name with the search box of the workspace.
      </p>
      <p className="mt-6 flex gap-4">
        <Link href="/dashboard" className="button">
          Back to the workspace
        </Link>
      </p>
    </main>
  );
}
