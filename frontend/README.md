# Lighthouse screen

The screen of the port desk. Every page is rendered on the server from the read-only routes of the API in `../backend`, and none writes.

| Page | Shows |
| --- | --- |
| `/` | Counts, a map of the ports of the world on the last day read, the ports that are unusual now, the overloaded berths of Finland, and the heaviest lessons |
| `/ports`, `/ports/[key]` | The ports of a country, busiest first; one port with its days, its episodes, what was learned about it, and the Finnish port calls that called there, came from there, or are bound there |
| `/berths` | The berth board of Finland: what each berth has held, and where more is expected |
| `/episodes`, `/episodes/[...id]` | Episodes by state and kind; one episode in order, each entry with its evidence |
| `/learned` | Lessons and playbooks with the episodes for and against them |
| `/portcalls/[id]` | One port call as it is, or as it was at a time, with its versions |

```bash
bun install
bun run dev        # http://localhost:3000
bun run build && bun run start
```

`LIGHTHOUSE_API` names the API; by default `http://127.0.0.1:8100`, where `uv run uvicorn app.main:app --port 8100` serves it from `../backend`.
