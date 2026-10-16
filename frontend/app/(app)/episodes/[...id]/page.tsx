import { Suspense } from "react";
import { redirect } from "next/navigation";
import { Loading } from "@/app/components/ui";
import { caseHref } from "@/app/lib/operations";
export default function EpisodePage(props: PageProps<"/episodes/[...id]">) {
  return (
    <Suspense fallback={<Loading what="the case" />}>
      <Forward {...props} />
    </Suspense>
  );
}
async function Forward({ params }: PageProps<"/episodes/[...id]">) {
  return redirect(
    caseHref((await params).id.map(decodeURIComponent).join("/")),
  );
}
