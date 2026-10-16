"use client";
import { Suspense, useState } from "react";
import GoogleError from "../GoogleError";
import GoogleButton from "../GoogleButton";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Eye, EyeOff, Waves } from "lucide-react";
import { Logo } from "../Logo";
export default function AccountForm({ signup = false }: { signup?: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [visible, setVisible] = useState(false);
  return (
    <main className="night console ops-auth">
      <section className="ops-auth-story">
        <Link href="/" className="ops-auth-brand">
          <Logo size={35} />
          <span>Lighthouse.</span>
        </Link>
        <div>
          <p className="ops-kicker">A clearer course.</p>
          <h1>
            The right context.
            <br />
            Your next decision.
          </h1>
          <p>
            Follow the ports that matter. Investigate with evidence. Keep every
            decision connected.
          </p>
          <div className="ops-auth-flow">
            <span>Observe</span>
            <i />
            <span>Investigate</span>
            <i />
            <span>Decide</span>
          </div>
        </div>
        <Waves size={45} />
      </section>
      <section className="ops-auth-form">
        <Link href="/" className="ops-back">
          ← Back to Lighthouse
        </Link>
        <div>
          <p className="ops-kicker">Your operations workspace</p>
          <h2>{signup ? "Make it your desk." : "Welcome back."}</h2>
          <p>
            {signup
              ? "Create your account to follow ports, investigate cases, and preserve your decisions."
              : "Sign in to your watchlist and pick up where you left off."}
          </p>
          <GoogleButton />
          <Suspense fallback={null}>
            <GoogleError />
          </Suspense>
          <div className="auth-divider">or continue with email</div>
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              setBusy(true);
              setError("");
              const fields = new FormData(event.currentTarget);
              try {
                const response = await fetch(
                  `/api/auth/${signup ? "register" : "login"}`,
                  {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(Object.fromEntries(fields)),
                  },
                );
                const data = await response.json();
                if (!response.ok) {
                  setError(data.detail ?? "Please try again.");
                  return;
                }
                router.push("/dashboard");
                router.refresh();
              } catch {
                setError("We couldn't connect just now. Please try again.");
              } finally {
                setBusy(false);
              }
            }}
          >
            {signup ? (
              <label>
                Your name
                <input
                  name="name"
                  required
                  maxLength={80}
                  autoComplete="name"
                />
              </label>
            ) : null}
            <label>
              Email address
              <input
                name="email"
                type="email"
                required
                maxLength={254}
                autoComplete="email"
                placeholder="you@company.com"
              />
            </label>
            <label>
              Password
              <div className="ops-auth-password">
                <input
                  name="password"
                  type={visible ? "text" : "password"}
                  required
                  minLength={12}
                  maxLength={128}
                  autoComplete={signup ? "new-password" : "current-password"}
                  placeholder={
                    signup ? "At least 12 characters" : "Your password"
                  }
                />
                <button
                  type="button"
                  aria-label={visible ? "Hide password" : "Show password"}
                  onClick={() => setVisible(!visible)}
                >
                  {visible ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
            </label>
            {error ? (
              <p role="alert" className="ops-form-error">
                {error}
              </p>
            ) : null}
            <button className="ops-primary" disabled={busy}>
              {busy ? "One moment…" : signup ? "Create account" : "Sign in"}
              <ArrowRight size={17} />
            </button>
          </form>
          <p className="ops-auth-switch">
            {signup ? "Already have an account?" : "New to Lighthouse?"}{" "}
            <Link href={signup ? "/login" : "/signup"}>
              {signup ? "Sign in" : "Create an account"}
            </Link>
          </p>
        </div>
      </section>
    </main>
  );
}
