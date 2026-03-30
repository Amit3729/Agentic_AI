# Agentic AI: Multi-Server MCP Assistant

## Overview
This project is an advanced, multi-agent assistant built using the **Model Context Protocol (MCP)**. It features a central AI orchestrator that communicates with multiple independent MCP servers to perform real-world tasks. The "brain" of the agent is powered by **Groq** (using the `llama-3.3-70b-versatile` model) for blazing-fast inference.

## Features & Capabilities
The assistant can autonomously decide which tools to use across a variety of domains. It currently connects to two distinct MCP servers:

### 1. General Info Server (`mcp_server/`)
*   **Live Weather Forecasts**: Fetches 1-7 day weather forecasts for any city globally using the free Open-Meteo API.
*   **Weather Alerts**: Retrieves active weather warnings for US states using the NWS API.
*   **Web Search**: Performs live internet searches via DuckDuckGo to answer questions about recent events.
*   **News Headlines**: Fetches the latest top news headlines via Google News RSS.

### 2. Google Calendar Server (`mcp_calendar/`)
*   **Read Schedule**: Lists your upcoming calendar events.
*   **Manage Schedule**: Adds new events, meetings, or reminders to your primary Google Calendar, and can delete them.
*   **Secure Auth**: Connects directly to your Google account using Desktop OAuth.

## Project Structure

```text
.
├── agent/
│   └── agent.py              # The Orchestrator AI. Connects to servers, manages the ReAct loop and history.
├── mcp_server/
│   └── server.py             # MCP Server 1: Weather, Web Search, and News tools.
├── mcp_calendar/
│   ├── calendar_server.py    # MCP Server 2: Google Calendar tools.
│   ├── client_secret.json    # (You provide this) Google OAuth Desktop credentials.
│   └── token.json            # (Auto-generated) Saves your login session.
├── .env                      # Environment variables (Groq API key).
├── requirements.txt          # Python dependencies.
└── README.md                 # This file.
```

## Prerequisites
*   Python 3.12+
*   A **Groq API Key** (Free at console.groq.com)
*   **Google Cloud Desktop OAuth Credentials** (Required ONLY if you want to use the Calendar features)

## Installation & Setup

1. **Clone the repository & install dependencies:**
   ```bash
   git clone git@github.com:Amit3729/Agentic_AI.git
   cd Agentic_AI
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables:**
   Create a `.env` file in the root directory and add your Groq API key:
   ```env
   GROQ_API_KEY=your_groq_api_key_here
   ```

3. **Set up Google Calendar (Optional but recommended):**
   * Go to the Google Cloud Console, create a project, and enable the **Google Calendar API**.
   * Go to **OAuth consent screen** -> set to "Testing" -> **Add your email to "Test users"**.
   * Go to **Credentials** -> Create OAuth client ID -> Application type: **Desktop app**.
   * Download the JSON file, rename it to `client_secret.json`, and place it inside the `mcp_calendar/` folder.

## Usage

Start the interactive terminal assistant:

```bash
python -m agent.agent
```

*First Run Note*: If you set up the Calendar credentials, the very first time you run the agent, it will open your web browser or prompt you in the console to log in to your Google Account. Once approved, it saves a `token.json` file so you won't have to log in repeatedly.

### Example Prompts to Try:
*   *"What's the weather like in Kathmandu this weekend? Should I pack an umbrella?"*
*   *"Search the web for the latest news about AI."*
*   *"What are the top news headlines today?"*
*   *"List my Google calendar events for tomorrow."*
*   *"Schedule a meeting titled 'AI Research Sync' for tomorrow at 2 PM for 1 hour."*

## How It Works (Under the Hood)

When you ask the agent a question, here is the flow (known as the **ReAct Loop**):

1. **Orchestration**: `agent.py` spawns both `mcp_server` and `mcp_calendar` as background subprocesses and communicates with them over standardized `stdio`.
2. **Tool Discovery**: The agent asks both servers, *"What tools do you have?"* and merges the lists (e.g., `get_forecast`, `search_web`, `add_event`).
3. **Reasoning**: Your question is sent to the Groq LLM along with the available tool schemas. The LLM decides what data it needs.
4. **Action**: The LLM outputs a `tool_use` request. `agent.py` looks at the tool name, figures out which server owns that tool, and forwards the request.
5. **Observation**: The specific target server (e.g., Calendar) executes the Python code, makes the external API call, and sends the raw data back to the agent.
6. **Response**: The agent feeds this data back to the LLM, which uses it to generate a final conversational answer for you.
