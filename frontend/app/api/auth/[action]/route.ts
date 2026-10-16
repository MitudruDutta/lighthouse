import { NextRequest, NextResponse } from "next/server";
import { AUTH_API, sameOrigin } from "@/app/lib/auth-server";
import { DESK_COOKIE } from "@/app/lib/api";
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ action: string }> },
) {
  const { action } = await params;
  if (!["register", "login", "logout"].includes(action))
    return NextResponse.json({ detail: "Not found." }, { status: 404 });
  if (!sameOrigin(request))
    return NextResponse.json(
      { detail: "Request not allowed." },
      { status: 403 },
    );
  try {
    const text = action === "logout" ? "" : await request.text();
    if (text.length > 4096)
      return NextResponse.json(
        { detail: "Request is too large." },
        { status: 413 },
      );
    const body = text ? JSON.parse(text) : undefined;
    const token = request.cookies.get(DESK_COOKIE)?.value;
    const response = await fetch(`${AUTH_API}/${action}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
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
      result.cookies.set(DESK_COOKIE, data.token, {
        httpOnly: true,
        sameSite: "strict",
        secure:
          request.nextUrl.protocol === "https:" ||
          request.headers.get("x-forwarded-proto") === "https",
        path: "/",
        maxAge: 604800,
      });
    if (action === "logout") result.cookies.delete(DESK_COOKIE);
    result.headers.set("Cache-Control", "no-store");
    return result;
  } catch {
    return NextResponse.json(
      { detail: "We couldn't connect just now. Please try again." },
      { status: 503 },
    );
  }
}
