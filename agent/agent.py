import asyncio
import json
import os 
import sys
from pathlib import Path

from groq import Groq
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv
load_dotenv()



# Paths to MCP servers
WEATHER_SERVER = Path(__file__).parent.parent / "mcp_server" / "server.py"
CALENDAR_SERVER = Path(__file__).parent.parent / "mcp_calendar" / "calendar_server.py"

# Which model to use
# Switch to a stronger instruction-following model on Groq to reduce hallucination
MODEL = "llama-3.3-70b-versatile"
 
# Instructions for the AI — this shapes how it behaves
# SYSTEM_PROMPT = """You are a helpful weather assistant.
# You have tools to get weather forecasts and alerts for any city.
 
# Rules:
# - Always call a tool before answering weather questions (never guess)
# - For weekend questions, call get_forecast with days=7, then look at Saturday/Sunday
# - Give practical advice (umbrella? jacket? cancel plans?)
# - Be brief and friendly
# """

# Instruction format optimization
# Ensure Groq gets clear explicit rules for function calls to avoid hallucinating "<function=...>"
SYSTEM_PROMPT = """You are an advanced AI assistant with real-world connectivity.
You have tools to check the weather, look up alerts, and search the open internet.

Rules:
- If asked about the weather, ALWAYS use the get_forecast tool.
- If asked about news, facts, people, or current events, ALWAYS use the search_web tool.
- Combine information when necessary (e.g., if checking weather for an event, search the web to find the event's location first).
- Be brief, helpful, and cite your sources if quoting web search results.

EXTREMELY IMPORTANT DO NOT HALLUCINATE TOOL CALLS:
- Your tool calls MUST ALWAYS be valid JSON.
- Never write `<function=...>` or `<foo>`.
- Use the correct explicit JSON format to submit function calls.
"""

def convert_tools_for_groq(mcp_tools):
    '''
    Convert MCP tools to Groq tool format.
    '''
    tools = []
    for tool in mcp_tools:
        # Hack to prevent Groq from failing on "integer" vs "string" issues
        # by treating integer parameter as number or string. 
        schema = dict(tool.inputSchema)
        if "properties" in schema:
            for k, v in schema["properties"].items():
                if v.get("type") == "integer":
                    v["type"] = "string"  # Llama sometimes generates string instead of int
        
        tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": schema,
            }
        })
    return tools

async def chat(mcp_session, groq_client, tools, history, user_message):
    '''
    Process a user message  throught the full ReACT loop:
    REACT loops steps:
    1. Add user message to history
    2. Ask groq for a response (which may include tool calls)
    3. if groq calls a tool, execute the tool and add the result to history, then repeat from step 2
    4. if groq gives a final answer, return it to the user
    '''
    #step 1: add user message to history
    if not history:
        history.append({"role": "system", "content": SYSTEM_PROMPT})
    history.append({"role": "user", "content": user_message})

    #Step 2: Loop  until we get a final answer from groq
    while True:
        # Ask Groq for a response
        try:
            # We strictly enforce that Groq should reply with the proper JSON function call array format.
            # Using JSON mode could help, but standard tools logic works best with clear API limits.
            response = groq_client.chat.completions.create(
                model=MODEL,
                max_tokens=2048,
                tools=tools,
                tool_choice="auto",
                messages=history
            )
        except Exception as e:
            # If Groq API fails (e.g. tool call hallucination format error), recover gracefully
            print(f"\n[API Error]: {e}")
            # remove the last user message that caused the error to avoid infinite loops if retried
            if history and history[-1]["role"] == "user":
                history.pop()
            return "Sorry, I encountered an internal error processing that request."

        message = response.choices[0].message
        
        #Did groq call a tool?
        if message.tool_calls:
            #save the tool call to history
            assistant_msg = {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    } for tc in message.tool_calls
                ]
            }
            history.append(assistant_msg)

            #Run each tool that groq  requested
            for tool_call in message.tool_calls:
                # Some models hallucinate invalid tool names, we can check if it exists
                valid_tool_names = [t["function"]["name"] for t in tools]
                if tool_call.function.name not in valid_tool_names:
                    print(f"\n  [Error] Model tried to call invalid tool: {tool_call.function.name}")
                    history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": f"Error: Tool {tool_call.function.name} does not exist.",
                    })
                    continue

                print(f"\n  [Tool called] {tool_call.function.name}")
                print(f"  [Arguments]   {tool_call.function.arguments}")

                #call the tool via mcp(send request to server.py)
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    print(f"\n  [Error] Invalid JSON arguments from model.")
                    history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": "Error: Invalid JSON arguments provided to tool.",
                    })
                    continue
                    
                # Ensure days is an int if it exists and is a string
                if 'days' in args and isinstance(args['days'], str) and args['days'].isdigit():
                    args['days'] = int(args['days'])
                
                result = await mcp_session.call_tool(tool_call.function.name, args)

                #Extract the text from the result
                result_text = ""
                for content in result.content:
                    if hasattr(content, "text"):
                        result_text += content.text
                print(f"  [Result]     {result_text[:80]}...") #print first 80 chars of result
                history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": result_text,
                })
        else:
            #Yes - return the answer to the user
            final_answer = message.content
            
            #Save Groq's final answer to history
            history.append({"role": "assistant", "content": final_answer})
            return final_answer


async def chat_router(weather_session, calendar_session, tools, history, groq_client, user_message):
    """
    Route tool calls to the correct MCP session by tool name.
    We keep a name->session map based on the merged tool list.
    """
    # Build a lookup from tool name to session
    tool_to_session = {}
    for t in tools:
        name = t["function"]["name"]
        # Heuristics: names from weather server vs calendar server
        if name in ("get_forecast", "get_alerts", "search_web", "get_news_headlines"):
            tool_to_session[name] = weather_session
        else:
            tool_to_session[name] = calendar_session

    # Wrapper that delegates call_tool to the right session
    class RoutedSession:
        async def call_tool(self, tool_name, args):
            session = tool_to_session.get(tool_name, weather_session)
            return await session.call_tool(tool_name, args)

    routed = RoutedSession()
    return await chat(routed, groq_client, tools, history, user_message)

async def main():
    #Check API
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("Error: Please set the GROQ_API_KEY environment variable.")
        sys.exit(1)
    claude = Groq(api_key=api_key)
    print("Starting MCP client...")

    # Launch MCP servers as subprocesses (weather + calendar)
    weather_parms = StdioServerParameters(command='python', args=[str(WEATHER_SERVER)])
    calendar_parms = StdioServerParameters(command='python', args=[str(CALENDAR_SERVER)])

    # Start both servers and create sessions
    async with stdio_client(weather_parms) as (w_read, w_write), stdio_client(calendar_parms) as (c_read, c_write):
        async with ClientSession(w_read, w_write) as weather_session, ClientSession(c_read, c_write) as calendar_session:
            # Initialize both sessions
            await weather_session.initialize()
            await calendar_session.initialize()

            # Gather tools from both
            weather_tools = await weather_session.list_tools()
            calendar_tools = await calendar_session.list_tools()

            # Build unified tool list for Groq
            merged_tools = convert_tools_for_groq(weather_tools.tools + calendar_tools.tools)

            print(f"Connected! Tools available: {[t['function']['name'] for t in merged_tools]}")
            print("-" * 50)
            print("Ask me anything! (type 'quit' to exit)")
            print("Examples: 'What's the forecast for Kathmandu?' or 'Add meeting tomorrow 10am-11am' or 'Show events today'")
            print("-" * 50)

            # conversation history
            history = []
            while True:
                user_input = input("\nYou: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ['quit', 'exit']:
                    print("bye!")
                    break
                # Route tool calls to the correct session inside chat: we keep both sessions and pass a small router
                answer = await chat_router(weather_session, calendar_session, merged_tools, history, claude, user_input)
                print(f"\nAI: {answer}")

if __name__ == "__main__":
    asyncio.run(main())


