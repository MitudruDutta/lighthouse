"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowUpRight, Eye, EyeOff, KeyRound, ShieldCheck } from "lucide-react";
import { Brand } from "./Brand";
export function AuthForm({ signup = false }: { signup?: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [visible, setVisible] = useState(false);
  return (
    <main id="main" className="auth-shell">
      <section className="auth-story">
        <Brand />
        <div>
          <span className="eyebrow">A LITTLE CONTINUITY GOES A LONG WAY.</span>
          <h1>
            Your next idea
            <br />
            deserves
            <br />
            <em>a memory.</em>
          </h1>
          <p>
            Facts with a history. Decisions with evidence. Context your agents
            can return to.
          </p>
          <div className="auth-story-diagram">
            <div>
              <span>01</span>Observe
            </div>
            <i />
            <div>
              <span>02</span>Remember
            </div>
            <i />
            <div>
              <span>03</span>Build on it
            </div>
          </div>
        </div>
        <small>Lighthouse Memory · Built on FalkorDB</small>
      </section>
      <section className="auth-form-section">
        <Link href="/" className="auth-back">
          ← Back to Lighthouse
        </Link>
        <div className="auth-form-wrap">
          <span className="form-symbol">
            <KeyRound size={23} />
          </span>
          <h2>{signup ? "Make room for memory." : "Welcome back."}</h2>
          <p>
            {signup
              ? "Create a private workspace. Your first project starts here."
              : "Sign in to your workspace and pick up where you left off."}
          </p>
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
                if (response.ok) {
                  router.push("/dashboard");
                  router.refresh();
                  return;
                }
                setError(data.detail ?? "Please try again.");
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
                  placeholder="How should we call you?"
                />
              </label>
            ) : null}
            <label>
              Email address
              <input
                type="email"
                name="email"
                required
                maxLength={254}
                autoComplete="email"
                placeholder="you@company.com"
              />
            </label>
            <label>
              Password
              <div className="password-field">
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
              {signup ? <small>Use at least 12 characters.</small> : null}
            </label>
            {error ? (
              <p className="form-error" role="alert">
                {error}
              </p>
            ) : null}
            <button className="button" disabled={busy}>
              {busy ? "One moment…" : signup ? "Create workspace" : "Sign in"}
              <ArrowUpRight size={15} />
            </button>
          </form>
          <p className="auth-switch">
            {signup ? "Already have an account?" : "New to Lighthouse?"}{" "}
            <Link href={signup ? "/login" : "/signup"}>
              {signup ? "Sign in" : "Create a workspace"}
            </Link>
          </p>
          <div className="auth-assurance">
            <ShieldCheck size={16} />
            <span>
              Private account. No card required. No paid plan activated.
            </span>
          </div>
        </div>
        <small className="auth-footnote">
          Local developer preview. Email verification and account recovery are
          not available yet.
        </small>
      </section>
    </main>
  );
}
