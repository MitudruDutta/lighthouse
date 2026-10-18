import { API, COOKIE } from "./server";
import { googleFlow } from "./google-server";
export const google = googleFlow(
  API + "/auth/google",
  COOKIE,
  process.env.MEMORY_SITE_URL ?? "https://lighthouse-memory.vercel.app",
  "/dashboard/settings",
);
