import { Suspense } from "react";
import Link from "next/link";
import type { Metadata } from "next";
import { Card, Loading } from "@/app/components/ui";
import ProfileForm from "@/app/components/operations/ProfileForm";
import { operations, operationsToken } from "@/app/lib/operations-server";
import { desk } from "@/app/lib/api";
import type { Profile } from "@/app/lib/operations";
export const metadata: Metadata = { title: "Profile" };
export default function ProfilePage() {
  return (
    <Suspense fallback={<Loading what="your workspace preferences" />}>
      <Body />
    </Suspense>
  );
}
async function Body() {
  const token = await operationsToken();
  const [profile, options, identity] = await Promise.all([
    operations<Profile>("profile"),
    operations<{
      ports: { key: string; name: string }[];
      vessels: { key: string; name: string }[];
    }>("watchlist-options"),
    desk<{ user: { name: string; email: string; google_connected: boolean } }>(
      "/api/auth/me",
      token ?? "",
    ),
  ]);
  if (!profile || !options)
    return (
      <Card title="Your workspace">
        <p>Sign in to personalize your watchlist.</p>
        <Link href="/login" className="ops-primary mt-4">
          Sign in →
        </Link>
      </Card>
    );
  return (
    <div className="ops-workspace">
      <header className="ops-page-heading">
        <div>
          <p className="ops-kicker">Your focus, remembered</p>
          <h1>Your profile. Your focus.</h1>
          <p>
            The ports you follow. The vessels you care about. The work that’s
            yours.
          </p>
        </div>
        <Link href="/dashboard" className="ops-outline">
          Back to attention queue →
        </Link>
      </header>
      <ProfileForm
        profile={profile}
        options={options}
        account={identity.ok ? identity.data.user : undefined}
      />
    </div>
  );
}
