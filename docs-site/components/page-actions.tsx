"use client";
import { Check, Copy } from "lucide-react";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { PARTS } from "@/app/pages";

export function PageTools() {
  const path = usePathname();
  const [copied, setCopied] = useState(false);
  const group =
    PARTS.find(([, pages]) => pages.some(([to]) => to === path))?.[0] ??
    "Documentation";
  return (
    <div className="page-tools">
      <span>{group}</span>
      <button
        type="button"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(
              document.querySelector<HTMLElement>(".lh-prose")?.innerText ?? "",
            );
            setCopied(true);
            setTimeout(() => setCopied(false), 1800);
          } catch {
            setCopied(false);
          }
        }}
      >
        {copied ? <Check size={13} /> : <Copy size={13} />}
        {copied ? "Copied" : "Copy page"}
      </button>
    </div>
  );
}
