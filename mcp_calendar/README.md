# MCP Google Calendar Server

Minimal MCP server exposing Google Calendar tools over stdio.

## Files
- `calendar_server.py` — MCP server with tools: `list_events`, `add_event`, `delete_event`.
- `client_secret.json` — OAuth client (Desktop) you download from Google Cloud (not in repo).
- `token.json` — Generated after first OAuth; keep it private / gitignored.

## Install deps
```
pip install google-auth-oauthlib google-api-python-client httpx mcp
```

## Run
```
python calendar_server.py
```
- First run opens a browser for consent; tokens saved to `token.json`.

## Tools
- `list_events(time_min, time_max, max_results=5)`
- `add_event(summary, start, end, description?, location?)`
- `delete_event(event_id)`

## Integrate with your agent
- Start this server via stdio (similar to your weather server) using `StdioServerParameters`.
- Add a prompt hint: “For scheduling/reminders, use the calendar tools.”
