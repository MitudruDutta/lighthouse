"use client";
import { useState } from "react";
import { Check, Copy } from "lucide-react";

/** The one command that installs the library, with a button that copies it. */
export function InstallCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="install-command not-prose">
      <code>
        <span aria-hidden>$ </span>
        {command}
      </code>
      <button
        type="button"
        aria-label={copied ? "Copied" : `Copy ${command}`}
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(command);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          } catch {
            setCopied(false);
          }
        }}
      >
        {copied ? <Check size={15} aria-hidden /> : <Copy size={15} aria-hidden />}
      </button>
    </div>
  );
}
