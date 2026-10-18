# Lighthouse Memory plugins

Each plugin connects an agent to a Lighthouse Memory project over MCP and adds a skill that tells the agent when to remember, when to recall first, and how to record work as episodes with evidence. The skill is the same in every plugin.

| Agent | Plugin | Format | Listed in |
| --- | --- | --- | --- |
| Claude Code | [`claude/lighthouse-memory`](claude/lighthouse-memory) | Claude Code plugin | `.claude-plugin/marketplace.json` |
| Cursor | [`cursor/lighthouse-memory`](cursor/lighthouse-memory) | Cursor plugin | `.cursor-plugin/marketplace.json` |
| Codex | [`codex/lighthouse-memory`](codex/lighthouse-memory) | Agent Plugins 1.0 | `.agents/plugins/marketplace.json` |

Every plugin needs a project API key: create a project and a key in the Lighthouse Memory console, under **API keys**.

## Claude Code

```text
/plugin install lighthouse-memory --marketplace MitudruDutta/lighthouse
```

Set the address and key before starting Claude Code:

```bash
export LIGHTHOUSE_MEMORY_URL=http://localhost:8200
export LIGHTHOUSE_API_KEY=YOUR_PROJECT_API_KEY
```

## Cursor

```bash
git clone https://github.com/MitudruDutta/lighthouse.git
mkdir -p ~/.cursor/plugins/local
cp -r lighthouse/plugins/cursor/lighthouse-memory ~/.cursor/plugins/local/
```

Run **Developer: Reload Window**, then set the plugin's `LIGHTHOUSE_API_KEY` variable under **Plugins**, **Configure**.

## Codex

```bash
codex plugin marketplace add MitudruDutta/lighthouse
```

Run `codex`, open `/plugins`, and install **Lighthouse Memory**. Codex asks for the project API key during installation. Start a new session to use it.

## Another address

The Cursor and Codex plugins connect to the local stack at `http://localhost:8200/mcp`. For a hosted instance, change `url` in the plugin's `mcp.json`. The Claude Code plugin reads its address from `LIGHTHOUSE_MEMORY_URL`.
