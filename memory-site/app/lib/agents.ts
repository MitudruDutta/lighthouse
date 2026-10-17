// How each agent client connects to a project's MCP endpoint with its API key. The key is
// either the one just created on the page or a placeholder the reader replaces.
export const PLACEHOLDER = "YOUR_PROJECT_API_KEY";
export const SERVER = "lighthouse-memory";

export type Client = {
  id: string;
  name: string;
  where: string;
  language: string;
  code: (url: string, key: string) => string;
  note?: string;
};

const json = (value: unknown) => JSON.stringify(value, null, 2);
const bearer = (key: string) => ({ Authorization: `Bearer ${key}` });

export const CLIENTS: Client[] = [
  {
    id: "claude-code",
    name: "Claude Code",
    where: "Run in your terminal",
    language: "bash",
    code: (url, key) =>
      `claude mcp add --transport http ${SERVER} ${url} \\\n  --header "Authorization: Bearer ${key}"`,
    note: "Add --scope project to share it with the repository through .mcp.json.",
  },
  {
    id: "claude-desktop",
    name: "Claude Desktop",
    where: "claude_desktop_config.json",
    language: "json",
    code: (url, key) =>
      json({
        mcpServers: {
          [SERVER]: {
            command: "npx",
            args: ["-y", "mcp-remote", url, "--header", `Authorization: Bearer ${key}`],
          },
        },
      }),
    note: "Needs Node.js. Restart Claude Desktop after saving.",
  },
  {
    id: "cursor",
    name: "Cursor",
    where: "~/.cursor/mcp.json or .cursor/mcp.json",
    language: "json",
    code: (url, key) => json({ mcpServers: { [SERVER]: { url, headers: bearer(key) } } }),
  },
  {
    id: "vscode",
    name: "VS Code",
    where: ".vscode/mcp.json",
    language: "json",
    code: (url, key) =>
      json({ servers: { [SERVER]: { type: "http", url, headers: bearer(key) } } }),
  },
  {
    id: "windsurf",
    name: "Windsurf",
    where: "~/.codeium/windsurf/mcp_config.json",
    language: "json",
    code: (url, key) =>
      json({ mcpServers: { [SERVER]: { serverUrl: url, headers: bearer(key) } } }),
  },
  {
    id: "codex",
    name: "Codex",
    where: "~/.codex/config.toml",
    language: "toml",
    code: (url) =>
      `[mcp_servers.${SERVER}]\nurl = "${url}"\nbearer_token_env_var = "LIGHTHOUSE_API_KEY"`,
    note: "Codex reads the key from the environment: export LIGHTHOUSE_API_KEY first.",
  },
  {
    id: "gemini",
    name: "Gemini CLI",
    where: "~/.gemini/settings.json",
    language: "json",
    code: (url, key) => json({ mcpServers: { [SERVER]: { httpUrl: url, headers: bearer(key) } } }),
  },
  {
    id: "python",
    name: "Python",
    where: "Any agent framework, with the MCP SDK",
    language: "python",
    code: (url, key) => `import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    headers = {"Authorization": "Bearer ${key}"}
    async with streamablehttp_client("${url}", headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            found = await session.call_tool("recall", {"query": "customer"})
            print(found.content[0].text)


asyncio.run(main())`,
  },
];

export const TOOLS: [string, boolean, string][] = [
  ["remember", true, "Save a memory or a new version of one"],
  ["recall", false, "Find memories by the words they hold"],
  ["history", false, "Every version of a memory, and when it held"],
  ["connection", false, "The chain of links between two memories"],
  ["open_episode", true, "Start a case to record work on"],
  ["record", true, "Add an observation or decision, with its evidence"],
  ["close_episode", true, "Close a case with its outcome"],
  ["episode", false, "A case with all its entries"],
  ["episodes_about", false, "The cases about one memory"],
  ["add_task", true, "Add work that any agent can claim"],
  ["claim_task", true, "Claim work; never two agents at once"],
  ["complete_task", true, "Finish a task you hold"],
  ["release_task", true, "Give a task back"],
  ["hand_off", true, "Pass work to another agent"],
  ["handoffs", false, "Work handed to you"],
  ["accept_handoff", true, "Take on work handed to you"],
];

export function rest(api: string, key: string) {
  return {
    curl: `curl ${api}/v1/memories \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{"key": "customer:acme", "title": "Acme", "text": "Renews in March. Prefers email."}'

curl "${api}/v1/memories?q=renews" -H "Authorization: Bearer ${key}"`,
    python: `import requests

API = "${api}"
headers = {"Authorization": "Bearer ${key}"}

requests.post(f"{API}/v1/memories", headers=headers, json={
    "key": "customer:acme",
    "title": "Acme",
    "text": "Renews in March. Prefers email.",
}).raise_for_status()

found = requests.get(f"{API}/v1/memories", headers=headers, params={"q": "renews"})
print(found.json()["data"])`,
    typescript: `const API = "${api}";
const headers = {
  Authorization: "Bearer ${key}",
  "Content-Type": "application/json",
};

await fetch(\`\${API}/v1/memories\`, {
  method: "POST",
  headers,
  body: JSON.stringify({
    key: "customer:acme",
    title: "Acme",
    text: "Renews in March. Prefers email.",
  }),
});

const found = await fetch(\`\${API}/v1/memories?q=renews\`, { headers });
console.log((await found.json()).data);`,
  };
}
