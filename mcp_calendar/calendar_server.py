import asyncio
import os
from datetime import datetime

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

# Google API client libs
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# OAuth scopes and file locations
SCOPES = ["https://www.googleapis.com/auth/calendar"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "client_secret.json")  # download from Google Cloud (Desktop OAuth)
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")               # generated after first consent

app = Server("google_calendar_server")


# ---------- Auth helpers ----------
def get_credentials():
    """Load/refresh OAuth credentials; prompt browser consent on first run."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # google-auth expects requests-compatible session; httpx works via built-in adapter
            creds.refresh(httpx.Client())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            use_console = os.environ.get("MCP_CALENDAR_CONSOLE_AUTH", "").lower() in {"1", "true", "yes"}
            try:
                creds = flow.run_console() if use_console else flow.run_local_server(port=0)
            except Exception:
                # Fallback when browser cannot open
                creds = flow.run_console()
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return creds


def get_service():
    creds = get_credentials()
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


# ---------- Tools ----------
@app.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="list_events",
            description="List events in a time window from primary calendar.",
            inputSchema={
                "type": "object",
                "properties": {
                    "time_min": {"type": "string", "description": "ISO time, e.g. 2026-03-30T00:00:00Z"},
                    "time_max": {"type": "string", "description": "ISO time, e.g. 2026-03-31T23:59:59Z"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["time_min", "time_max"]
            }
        ),
        types.Tool(
            name="add_event",
            description="Add an event to primary calendar.",
            inputSchema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Title"},
                    "start": {"type": "string", "description": "ISO start (e.g. 2026-03-30T10:00:00+05:45)"},
                    "end": {"type": "string", "description": "ISO end"},
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                },
                "required": ["summary", "start", "end"]
            }
        ),
        types.Tool(
            name="delete_event",
            description="Delete an event by ID from primary calendar.",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "Calendar event ID"},
                },
                "required": ["event_id"]
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "list_events":
        result = await run_list_events(arguments)
    elif name == "add_event":
        result = await run_add_event(arguments)
    elif name == "delete_event":
        result = await run_delete_event(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")
    return [types.TextContent(type="text", text=result)]


# ---------- Tool logic ----------
async def run_list_events(args: dict) -> str:
    svc = get_service()
    time_min = args["time_min"]
    time_max = args["time_max"]
    max_results = int(args.get("max_results", 5))
    events_result = svc.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    items = events_result.get("items", [])
    if not items:
        return "No events found."
    lines = []
    for ev in items:
        start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date")
        end = ev.get("end", {}).get("dateTime") or ev.get("end", {}).get("date")
        lines.append(f"- {ev.get('summary','(no title)')} | {start} → {end} | id={ev.get('id')}")
    return "\n".join(lines)


async def run_add_event(args: dict) -> str:
    svc = get_service()
    body = {
        "summary": args["summary"],
        "start": {"dateTime": args["start"]},
        "end": {"dateTime": args["end"]},
    }
    if "description" in args:
        body["description"] = args["description"]
    if "location" in args:
        body["location"] = args["location"]
    ev = svc.events().insert(calendarId="primary", body=body).execute()
    return f"Created event '{ev.get('summary')}' id={ev.get('id')} at {ev.get('htmlLink')}"


async def run_delete_event(args: dict) -> str:
    svc = get_service()
    event_id = args["event_id"]
    svc.events().delete(calendarId="primary", eventId=event_id).execute()
    return f"Deleted event {event_id}"


# ---------- Start server ----------
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
