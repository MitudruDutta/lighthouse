"use client";
import { useActionState, useState, useTransition } from "react";
import GoogleButton from "../GoogleButton";
import { useFormStatus } from "react-dom";
import { ArrowRight, Check, Search, Ship, Star, X } from "lucide-react";
import { saveProfile, saveWatchlist } from "@/app/(app)/profile/actions";
import type { Profile } from "@/app/lib/operations";
type Option = { key: string; name: string };
function Save() {
  const { pending } = useFormStatus();
  return (
    <button className="ops-primary" disabled={pending}>
      {pending ? "Saving…" : "Save my workspace"}
      <ArrowRight size={17} />
    </button>
  );
}
export default function ProfileForm({
  profile,
  options,
  account,
}: {
  profile: Profile;
  account?: { name: string; email: string; google_connected: boolean };
  options: { ports: Option[]; vessels: Option[] };
}) {
  const [state, action] = useActionState(saveProfile, {});
  const [ports, setPorts] = useState(profile.ports);
  const [vessels, setVessels] = useState(profile.vessels);
  // Following saves at once; a refused change is taken back.
  const [watch, setWatch] = useState<{ error?: string; saved?: string }>({});
  const [saving, startSaving] = useTransition();
  function follow(nextPorts: string[], nextVessels: string[]) {
    const before = [ports, vessels];
    setPorts(nextPorts);
    setVessels(nextVessels);
    startSaving(async () => {
      const result = await saveWatchlist(nextPorts, nextVessels);
      setWatch(result);
      if (result.error) {
        setPorts(before[0]);
        setVessels(before[1]);
      }
    });
  }
  const [kind, setKind] = useState<"ports" | "vessels">("ports");
  const [query, setQuery] = useState("");
  const selected = kind === "ports" ? ports : vessels;
  const setSelected = (next: string[]) =>
    kind === "ports" ? follow(next, vessels) : follow(ports, next);
  const found = options[kind]
    .filter((o) =>
      `${o.name} ${o.key}`.toLowerCase().includes(query.toLowerCase()),
    )
    .slice(0, 8);
  const zones = [
    ...new Set([
      profile.timezone,
      "UTC",
      "Europe/Helsinki",
      "Europe/London",
      "Europe/Athens",
      "Asia/Kolkata",
      "Asia/Singapore",
      "America/New_York",
      "America/Los_Angeles",
      "Australia/Sydney",
    ]),
  ];
  return (
    <form action={action} className="ops-profile-form">
      <input name="ports" type="hidden" value={JSON.stringify(ports)} />
      <input name="vessels" type="hidden" value={JSON.stringify(vessels)} />
      <div className="ops-profile-grid">
        <section className="ops-panel">
          <p className="ops-kicker">01 / Your preferences</p>
          <h2>A workspace that fits your day.</h2>
          <p className="ops-panel-intro">
            Choose how your attention queue opens and which timezone it uses.
          </p>
          {account ? (
            <div className="ops-account-summary">
              <span className="ops-kicker">Your Lighthouse account</span>
              <strong>{account.name}</strong>
              <span>{account.email}</span>
              {account.google_connected ? (
                <span className="google-connected">
                  <Check size={15} />
                  Google connected
                </span>
              ) : null}
            </div>
          ) : null}
          <label>
            Display name
            <input
              name="name"
              defaultValue={profile.name}
              required
              maxLength={100}
              autoComplete="name"
            />
          </label>
          <label>
            Timezone
            <select
              aria-label="Timezone"
              name="timezone"
              defaultValue={profile.timezone}
            >
              {zones.map((zone) => (
                <option key={zone}>{zone}</option>
              ))}
            </select>
          </label>
          <label>
            Default coverage
            <select
              aria-label="Default coverage"
              name="focus"
              defaultValue={profile.focus}
            >
              <option value="all">All coverage</option>
              <option value="finland">Finnish arrivals</option>
              <option value="global">Global trends</option>
            </select>
          </label>
          <label>
            Open my workspace on
            <select
              aria-label="Open my workspace on"
              name="view"
              defaultValue={profile.view ?? "attention"}
            >
              <option value="attention">All cases needing attention</option>
              <option value="watching">My followed ports and vessels</option>
              <option value="mine">Cases assigned to me</option>
            </select>
          </label>
          {!account?.google_connected ? (
            <div className="ops-profile-google">
              <p>Connect your matching Google account for faster sign-in.</p>
              <GoogleButton connect />
            </div>
          ) : null}
          <div className="ops-profile-summary">
            <Star size={22} />
            <strong>{ports.length + vessels.length}</strong>
            <span>ports and vessels in your watchlist</span>
          </div>
        </section>
        <section className="ops-panel">
          <p className="ops-kicker">02 / Follow what matters</p>
          <h2>Your watchlist.</h2>
          <p className="ops-panel-intro">
            Follow a port or vessel. Related cases appear under Watching in your
            attention queue.
          </p>
          <div className="ops-tabs">
            {(["ports", "vessels"] as const).map((k) => (
              <button
                key={k}
                type="button"
                aria-pressed={kind === k}
                onClick={() => {
                  setKind(k);
                  setQuery("");
                }}
              >
                {k === "ports" ? "Ports" : "Vessels"}
              </button>
            ))}
          </div>
          <p className="ops-watch-status" role="status" aria-live="polite">
            {saving
              ? "Saving…"
              : watch.error
                ? watch.error
                : watch.saved
                  ? "Saved. Related cases appear under Watching."
                  : "Following saves at once."}
          </p>
          <div className="ops-watch-chips">
            {selected.map((key) => (
              <span key={key}>
                {options[kind].find((o) => o.key === key)?.name ?? key}
                <button
                  type="button"
                  aria-label={`Unfollow ${key}`}
                  onClick={() => setSelected(selected.filter((s) => s !== key))}
                >
                  <X size={13} />
                </button>
              </span>
            ))}
          </div>
          <label className="ops-watch-search">
            <Search size={17} />
            <input
              aria-label={`Find ${kind}`}
              placeholder={`Search ${kind} by name or identifier…`}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div className="ops-watch-results">
            {found.map((o) => (
              <button
                type="button"
                key={o.key}
                disabled={selected.length >= 50 && !selected.includes(o.key)}
                aria-pressed={selected.includes(o.key)}
                onClick={() =>
                  setSelected(
                    selected.includes(o.key)
                      ? selected.filter((k) => k !== o.key)
                      : [...selected, o.key],
                  )
                }
              >
                <i>
                  {kind === "ports" ? <Star size={16} /> : <Ship size={16} />}
                </i>
                <span>
                  <strong>{o.name}</strong>
                  <small>{o.key}</small>
                </span>
                {selected.includes(o.key) ? (
                  <Check size={17} />
                ) : (
                  <span className="ops-follow-label">Follow</span>
                )}
              </button>
            ))}
            {!found.length ? (
              <p>No matching {kind} in the current data.</p>
            ) : null}
          </div>
        </section>
      </div>
      <div className="ops-profile-save">
        <Save />
        {state.error ? (
          <p role="alert" className="ops-form-error">
            {state.error}
          </p>
        ) : state.saved ? (
          <p role="status" className="ops-form-success">
            {state.saved}
          </p>
        ) : (
          <p>Update your watchlist as your focus changes.</p>
        )}
      </div>
    </form>
  );
}
