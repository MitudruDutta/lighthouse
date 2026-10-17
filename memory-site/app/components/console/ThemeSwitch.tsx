"use client";

import { Check, Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { DARK, THEME_KEY as KEY } from "../../lib/theme";

// Light, dark, or as the system says. The choice is kept by the browser; the theme itself
// is on <html data-theme>, set before the first paint by THEME_SCRIPT in the layout.
const EVENT = "lighthouse-theme-change";
type Choice = "system" | "light" | "dark";
const CHOICES: [Choice, string, typeof Sun][] = [
  ["system", "System", Monitor],
  ["light", "Light", Sun],
  ["dark", "Dark", Moon],
];

function chosen(): Choice {
  try {
    const value = window.localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

function apply(choice: Choice) {
  const dark = choice === "dark" || (choice === "system" && window.matchMedia(DARK).matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

function choose(choice: Choice) {
  try {
    window.localStorage.setItem(KEY, choice);
  } catch {}
  apply(choice);
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(listener: () => void) {
  const media = window.matchMedia(DARK);
  const changed = () => {
    apply(chosen());
    listener();
  };
  window.addEventListener("storage", changed);
  window.addEventListener(EVENT, changed);
  media.addEventListener("change", changed);
  return () => {
    window.removeEventListener("storage", changed);
    window.removeEventListener(EVENT, changed);
    media.removeEventListener("change", changed);
  };
}

// `label` shows the choice beside the icon; `up` opens the list above the button.
export function ThemeMenu({
  className,
  label = false,
  up = false,
}: {
  className?: string;
  label?: boolean;
  up?: boolean;
}) {
  const current = useSyncExternalStore(subscribe, chosen, () => "system" as Choice);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  const [, name, Icon] = CHOICES.find(([id]) => id === current) ?? CHOICES[0];
  return (
    <div className="theme-menu" ref={box}>
      <button
        type="button"
        className={className}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Theme: ${name}`}
        title={`Theme: ${name}`}
        onClick={() => setOpen(!open)}
      >
        <Icon size={17} />
        {label ? <span>Theme: {name}</span> : null}
      </button>
      {open ? (
        <div className="theme-menu-list" data-up={up || undefined} role="menu" aria-label="Theme">
          {CHOICES.map(([id, text, ChoiceIcon]) => (
            <button
              key={id}
              type="button"
              role="menuitemradio"
              aria-checked={current === id}
              onClick={() => {
                choose(id);
                setOpen(false);
              }}
            >
              <ChoiceIcon size={15} />
              <span>{text}</span>
              {current === id ? <Check size={14} /> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

// The same choice as three buttons, for a settings page.
export function ThemeChoice() {
  const current = useSyncExternalStore(subscribe, chosen, () => "system" as Choice);
  return (
    <div className="cx-tabs cx-theme-choice" role="radiogroup" aria-label="Theme">
      {CHOICES.map(([id, text, ChoiceIcon]) => (
        <button
          key={id}
          type="button"
          role="radio"
          aria-checked={current === id}
          onClick={() => choose(id)}
        >
          <ChoiceIcon size={14} />
          {text}
        </button>
      ))}
    </div>
  );
}
