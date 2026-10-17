import { NextRequest, NextResponse } from "next/server";
import { API, COOKIE, clientHeaders, sameOrigin } from "@/app/lib/server";
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ action: string }> },
) {
  const { action } = await params;
  if (!["login", "register", "logout"].includes(action))
    return NextResponse.json({ detail: "Not found." }, { status: 404 });
  if (!sameOrigin(request))
    return NextResponse.json(
      { detail: "Request not allowed." },
      { status: 403 },
    );
  if (Number(request.headers.get("content-length") ?? 0) > 4096)
    return NextResponse.json(
      { detail: "Request is too large." },
      { status: 413 },
    );
  try {
    const body = action === "logout" ? undefined : await request.json();
    const token = request.cookies.get(COOKIE)?.value;
    const response = await fetch(`${API}/auth/${action}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...clientHeaders(request),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });
    const data = await response.json();
    const result = NextResponse.json(
      response.ok
        ? { user: data.user, signed_out: data.signed_out }
        : { detail: data.detail ?? "Please try again." },
      { status: response.status },
    );
    if (response.ok && data.token)
      result.cookies.set(COOKIE, data.token, {
        httpOnly: true,
        // Lax, not strict: a strict cookie is left out when a page is reached from another
        // site, and again on every reload of that page, which signs the person out.
        // Requests that change anything are checked for this site's origin instead.
        sameSite: "lax",
        // Behind a proxy that ends TLS, the request reaches this server as http.
        secure:
          request.nextUrl.protocol === "https:" ||
          request.headers.get("x-forwarded-proto") === "https",
        path: "/",
        maxAge: 604800,
      });
    if (action === "logout") result.cookies.delete(COOKIE);
    result.headers.set("Cache-Control", "no-store");
    return result;
  } catch {
    return NextResponse.json(
      { detail: "We couldn't connect just now. Please try again." },
      { status: 503 },
    );
  }
}
