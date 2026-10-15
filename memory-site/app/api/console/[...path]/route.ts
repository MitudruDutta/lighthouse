import { NextRequest, NextResponse } from "next/server";
import { API, COOKIE, sameOrigin } from "@/app/lib/server";
async function proxy(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const token = request.cookies.get(COOKIE)?.value;
  if (!token)
    return NextResponse.json({ detail: "Please sign in." }, { status: 401 });
  if (request.method !== "GET" && !sameOrigin(request))
    return NextResponse.json(
      { detail: "Request not allowed." },
      { status: 403 },
    );
  if (Number(request.headers.get("content-length") ?? 0) > 65536)
    return NextResponse.json(
      { detail: "Request is too large." },
      { status: 413 },
    );
  const { path } = await params;
  try {
    const body = request.method === "GET" ? undefined : await request.text();
    if (body && body.length > 65536)
      return NextResponse.json(
        { detail: "Request is too large." },
        { status: 413 },
      );
    const response = await fetch(
      `${API}/console/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`,
      {
        method: request.method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: body || undefined,
        cache: "no-store",
        signal: AbortSignal.timeout(20000),
      },
    );
    const result = NextResponse.json(await response.json(), {
      status: response.status,
    });
    result.headers.set("Cache-Control", "no-store");
    return result;
  } catch {
    return NextResponse.json(
      { detail: "We couldn't connect just now. Please try again." },
      { status: 503 },
    );
  }
}
export { proxy as GET, proxy as POST, proxy as PATCH, proxy as DELETE };
