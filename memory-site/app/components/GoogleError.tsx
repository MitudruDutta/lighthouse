"use client";
import { useSearchParams } from "next/navigation";
export default function GoogleError() {
  const code = useSearchParams().get("google");
  if (!code) return null;
  const message =
    code === "cancelled"
      ? "Google sign-in was cancelled. You can try again."
      : code === "existing"
        ? "Sign in with your password, then connect the matching Google account from your profile."
        : code === "unavailable"
          ? "Google sign-in is temporarily unavailable. Please try again shortly."
          : "Google sign-in could not be completed. Please start again.";
  return (
    <p role="alert" className="google-auth-error">
      {message}
    </p>
  );
}
