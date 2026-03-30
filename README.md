# How It Works — Full Concept Guide

Read this before looking at any code.
Every concept is explained simply with a real example from this project.

---

## The Big Picture

When you ask "Should I pack an umbrella in Kathmandu this weekend?"
here is what actually happens:

```
YOU
 |
 | "Should I pack an umbrella this weekend?"
 v
AGENT (agent/agent.py)
 |
 | Sends your question to Claude (Anthropic AI)
 v
CLAUDE (the AI brain)
 |
 | "I need weather data. I will call get_forecast."
 v
MCP SERVER (mcp_server/server.py)
 |
 | Fetches real data from Open-Meteo (free weather API)
 v
WEATHER DATA comes back
 |
 v
CLAUDE reads the data and reasons:
 "Saturday has 75% rain chance. Yes, take an umbrella."
 |
 v
YOU get the answer
```

That whole flow is called the ReAct Loop.
Let's understand each piece.

---

## Concept 1: The MCP Server

MCP = Model Context Protocol (invented by Anthropic, now open standard)

Think of the MCP server as a toolbox.
It does NOT contain any AI.
It just exposes tools that an AI can call.

Our MCP server exposes 2 tools:
- get_forecast(city, days)  — fetches the forecast
- get_alerts(city)          — checks for weather warnings

The server does 3 things:
1. Tells the AI what tools exist (list_tools)
2. Runs the tools when the AI calls them (call_tool)
3. Returns the result to the AI

File to look at: mcp_server/server.py

Key code pattern:
```python
@app.list_tools()            # "Here are my tools"
async def list_tools():
    return [Tool(name="get_forecast", ...)]

@app.call_tool()             # "Run this tool"
async def call_tool(name, arguments):
    result = await run_get_forecast(arguments)
    return [TextContent(text=result)]
```

---

## Concept 2: Tools and Tool Schemas

A "tool" is just a function the AI is allowed to call.

Each tool has 3 parts:
- name        — what the AI calls it by (e.g. "get_forecast")
- description — tells the AI WHEN to use it (very important!)
- inputSchema — what parameters it accepts

The description is what Claude reads to decide:
"Does my current question need this tool?"

Example from our project:
```python
Tool(
    name="get_forecast",
    description="Get the weather forecast for a city (1-7 days).
                 Use this for questions like 'what is the weather this weekend'.",
    inputSchema={
        "type": "object",
        "properties": {
            "city": {"type": "string"},
            "days": {"type": "integer", "default": 3}
        },
        "required": ["city"]
    }
)
```

Claude reads that description and knows:
"If someone asks about the weekend weather, I should call get_forecast."

---

## Concept 3: The ReAct Loop

ReAct = Reason + Act

This is the core pattern of almost every AI agent.

Step 1 — REASON
  Claude reads your question and decides what to do.
  "The user wants weekend weather. I need forecast data."

Step 2 — ACT
  Claude calls a tool.
  It returns a tool_use block (not a text answer yet).
  { type: "tool_use", name: "get_forecast", input: {city: "Kathmandu", days: 7} }

Step 3 — OBSERVE
  Our agent runs the tool via the MCP server.
  The real weather data comes back.
  We send it back to Claude as a tool_result.

Step 4 — REPEAT or ANSWER
  If Claude needs more data, it calls another tool (loop again).
  If it has enough, it writes the final answer.

In agent.py, the ReAct loop is the while True: block:
```python
while True:
    response = claude.messages.create(...)

    if response.stop_reason == "end_turn":
        return final_answer       # Done!

    elif response.stop_reason == "tool_use":
        result = await mcp_session.call_tool(...)
        # Send result back and loop again
```

---

## Concept 4: The MCP Client

The MCP client is the "connector" between the agent and the server.

It does 3 things:
1. Spawns the MCP server as a subprocess (background process)
2. Does a handshake to establish the connection
3. Lets you call tools with: session.call_tool(name, arguments)

Communication happens over stdio (stdin/stdout).
The client writes JSON requests, the server writes JSON responses.
You never see this — the MCP library handles it automatically.

File to look at: agent/agent.py

Key code:
```python
# Launch the server subprocess
server_params = StdioServerParameters(command="python", args=["server.py"])

# Connect to it
async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()           # handshake
        tools = await session.list_tools()   # discover tools
        result = await session.call_tool(    # run a tool
            "get_forecast",
            {"city": "Kathmandu", "days": 7}
        )
```

---

## Concept 5: Tool Use / Function Calling

Tool use is the mechanism that lets Claude call external functions.

Normally Claude can only generate text.
With tools, it can say: "I want to call this function with these arguments."

How it works:
1. You pass tools to Claude when calling the API
2. Claude returns a tool_use block (not a text answer)
3. Your code runs the function
4. You send the result back to Claude
5. Claude reads it and writes the final answer

This is also called "function calling" — same concept, different name.

The AI never calls the tool directly.
Your code runs it and hands the result back.
Claude is always in control of deciding what to call and when.

---

## Concept 6: Conversation History

The AI has no memory between API calls.
Every time you call Claude, it only knows what you send it.

To give the agent memory, we keep a list of all messages:
```
history = [
    {"role": "user",      "content": "What is the weather in Kathmandu?"},
    {"role": "assistant", "content": [tool_use block]},
    {"role": "user",      "content": [tool_result]},
    {"role": "assistant", "content": "It is 18 degrees and partly cloudy..."},
    {"role": "user",      "content": "What about tomorrow?"},   <- next question
]
```

Every time the user asks a new question, we append to this list
and send the whole thing to Claude. This is how it remembers context.

---

## Concept 7: The Orchestrator Agent

In this project, agent.py is the Orchestrator.

An Orchestrator is the "manager agent" that:
- Receives the user's goal
- Decides which tools or sub-agents to use
- Coordinates everything
- Returns the final answer

In bigger projects, the orchestrator might manage multiple
specialist agents (researcher, coder, writer, etc.).
Here it just manages one MCP server with 2 tools.
Same concept, simpler scale.

---

## What Happens When You Ask a Question

Let's trace through:
"What is the forecast for Kathmandu this weekend?"

1. You type it in agent.py
2. agent.py appends it to history
3. agent.py calls Claude with history + available tools
4. Claude reads: "get_forecast is for weekend weather questions"
5. Claude returns: tool_use { name: "get_forecast", input: {city: "Kathmandu", days: 7} }
6. agent.py calls mcp_session.call_tool("get_forecast", {...})
7. MCP sends it to server.py (running as subprocess)
8. server.py calls Open-Meteo API over the internet
9. Gets back 7 days of weather data
10. Returns it as text
11. agent.py sends it back to Claude as a tool_result
12. Claude reads the forecast, sees rain on Saturday (75%)
13. Claude writes: "Yes, bring an umbrella. Saturday has a 75% chance of rain..."
14. agent.py prints that to you

Total: 2 API calls (one to discover tools, one to Claude x2 turns)
Real weather data, real AI reasoning, real answer.

---

## The Two Free APIs Used

Open-Meteo Geocoding  https://geocoding-api.open-meteo.com
  Converts "Kathmandu" to latitude 27.7, longitude 85.3

Open-Meteo Forecast   https://api.open-meteo.com
  Returns temperature, rain probability, wind speed, etc.
  by coordinates

No account needed. No API key. Completely free.