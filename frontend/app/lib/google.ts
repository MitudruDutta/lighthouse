import { AUTH_API } from "./auth-server";
import { DESK_COOKIE } from "./api";
import { googleFlow } from "./google-server";
export const google = googleFlow(
  AUTH_API + "/google",
  DESK_COOKIE,
  process.env.LIGHTHOUSE_APP_URL ?? "https://lighthouse-intelligence.vercel.app",
  "/profile",
);
