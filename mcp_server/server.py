import asyncio
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

from duckduckgo_search import DDGS


#create mcp
app = Server("weather_server")

#helper
WMO_CODES = {
    0:  "Clear sky",
    1:  "Mainly clear",
    2:  "Partly cloudy",
    3:  "Overcast",
    45: "Foggy",
    51: "Light drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    80: "Rain showers",
    95: "Thunderstorm",
}

def weather_description(code: int) -> str:
    return WMO_CODES.get(code, "Unknown")

#the forcast api need latitude and longitude, not a city name
#conversts city name to lat and long

async def get_coordinates(city: str) -> dict:
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        data = response.json()
    if not data.get("results"):
        return None
    r = data['results'][0]
    return{
        'lat': r['latitude'],
        'long': r['longitude'],
        'name': r['name'],
        'country': r.get('country',''),
        'timezone': r.get('timezone','auto'),

    }
#Tool defination
@app.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="get_forecast",
            description=(
                "Get the current weather for a given city. "
                "Returns daily temperature, weather code, and a human-readable description of the weather condition. "
                "use this for questions like 'whats the wather in this weekend'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "The name of the city to get the weather for."},
                    "days": {
                        "type": "integer",
                        "description": "How many days to forecast(1-7)",
                        "default": 3
                    }
                },
                "required": ["city"]
            }
        ),
        types.Tool(
            name="get_alerts",
            description=(
                "Get current weather alerts for a given city. "
                "Returns a list of active weather alerts, including the alert type, severity, and description. "
                "use this for questions like 'are there any weather alerts for this weekend?'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "The name of the city to get weather alerts for."}
                },
                "required": ["city"]
            }
        ),
        types.Tool(
            name="search_web",
            description=(
                "Search the web for current events, news or general knowledge."
                "Returns the top search results including title, snippet, and URL."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query(e.g 'Latest tech news' or 'political news of nepal')"
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="get_news_headlines",
            description=(
                "Fetch recent news headlines for a given topic (Google News RSS). "
                "Returns up to 10 headlines with title and URL."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Topic to search, e.g. 'Nepal politics'"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of headlines to return (1-10)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        )
    ]

#Tool Execution
@app.call_tool()
async def call_tool(name: str, arguments: dict)->list[types.TextContent]:
    if name == "get_forecast":
        result = await run_get_forecast(arguments)
    elif name == "get_alerts":
        result = await run_get_alerts(arguments)
    elif name == "search_web":
        result =  await run_web_search(arguments)
    elif name == "get_news_headlines":
        result = await run_get_news_headlines(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")
    return[types.TextContent(type="text", text=result)]

#TOOL LOGIC
async def run_get_forecast(args: dict) -> str:
    city = args.get("city", "").strip()
    days = int(args.get("days", 3))
    days = max(1, min(days, 7))  # clamp between 1 and 7
 
    coords = await get_coordinates(city)
    if not coords:
        return f"City not found: '{city}'"
 
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={coords['lat']}&longitude={coords['long']}"
        f"&daily=weathercode,temperature_2m_max,temperature_2m_min,"
        f"precipitation_probability_max,precipitation_sum"
        f"&timezone={coords['timezone']}"
        f"&forecast_days={days}"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        data = response.json()
 
    daily      = data.get("daily", {})
    dates      = daily.get("time", [])
    max_temps  = daily.get("temperature_2m_max", [])
    min_temps  = daily.get("temperature_2m_min", [])
    rain_prob  = daily.get("precipitation_probability_max", [])
    rain_mm    = daily.get("precipitation_sum", [])
    codes      = daily.get("weathercode", [])
 
    location = f"{coords['name']}, {coords['country']}"
    lines = [f"Weather Forecast — {location} ({days} days)\n"]
 
    for i in range(len(dates)):
        condition = weather_description(codes[i] if i < len(codes) else 0)
        max_t   = f"{max_temps[i]:.1f}" if i < len(max_temps) and max_temps[i] is not None else "?"
        min_t   = f"{min_temps[i]:.1f}" if i < len(min_temps) and min_temps[i] is not None else "?"
        prob    = rain_prob[i] if i < len(rain_prob) else 0
        mm      = f"{rain_mm[i]:.1f}" if i < len(rain_mm) and rain_mm[i] is not None else "0"
 
        lines.append(
            f"  {dates[i]}\n"
            f"    Condition:   {condition}\n"
            f"    Temp:        {min_t}°C – {max_t}°C\n"
            f"    Rain chance: {prob}%  ({mm} mm)\n"
        )
 
    return "\n".join(lines)
 
 
async def run_get_alerts(args: dict) -> str:
    city = args.get("city", "").strip()
 
    coords = await get_coordinates(city)
    if not coords:
        return f"City not found: '{city}'"
 
    # Fetch 7-day forecast to check for dangerous conditions
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"&latitude={coords['lat']}&longitude={coords['long']}"
        f"&daily=weathercode,temperature_2m_max,temperature_2m_min,"
        f"precipitation_probability_max,wind_speed_10m_max"
        f"&timezone={coords['timezone']}"
        f"&forecast_days=7"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        data = response.json()
 
    daily      = data.get("daily", {})
    dates      = daily.get("time", [])
    max_temps  = daily.get("temperature_2m_max", [])
    min_temps  = daily.get("temperature_2m_min", [])
    rain_probs = daily.get("precipitation_probability_max", [])
    winds      = daily.get("wind_speed_10m_max", [])
    codes      = daily.get("weathercode", [])
 
    alerts = []
    for i, date in enumerate(dates):
        if i < len(rain_probs) and rain_probs[i] >= 80:
            alerts.append(f"  [{date}] HEAVY RAIN — {rain_probs[i]}% chance of rain")
        if i < len(max_temps) and max_temps[i] is not None and max_temps[i] >= 38:
            alerts.append(f"  [{date}] EXTREME HEAT — {max_temps[i]:.1f}°C expected")
        if i < len(min_temps) and min_temps[i] is not None and min_temps[i] <= 0:
            alerts.append(f"  [{date}] FROST WARNING — {min_temps[i]:.1f}°C expected")
        if i < len(codes) and codes[i] in (95, 96, 99):
            alerts.append(f"  [{date}] THUNDERSTORM — severe weather likely")
        if i < len(winds) and winds[i] is not None and winds[i] >= 50:
            alerts.append(f"  [{date}] STRONG WIND — {winds[i]:.0f} km/h expected")
 
    location = f"{coords['name']}, {coords['country']}"
    if not alerts:
        return f"Weather Alerts — {location}\n\n  No alerts for the next 7 days. Conditions look normal."
 
    return f"Weather Alerts — {location}\n\n" + "\n".join(alerts)

async def run_web_search(args: dict)-> str:
    query = args.get("query", "").strip()
    if not query:
        return "Error: No search query provided."
    
    #Define a helper to run the synchronous DuckDuckGo seach
    def _search():
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=3))
    try:
        #Run the searcg in a bg thread to avoid blocking the event loop
        results = await asyncio.to_thread(_search)

        if not results:
            return f"No results found for query: '{query}"
        
        #Format the results into a readable string for LLM
        lines = [f"Web Search Results for: '{query}'\n"]
        for i , r in enumerate(results, 1):
            lines.append(f"Result {i}:")
            lines.append(f"Title:{r.get('title')}")
            lines.append(f" URL:{r.get('href')}")
            lines.append(f" Snippet:{r.get('body')}\n")
            
        return "\n".join(lines)
    except Exception as e:
        return f" Web search failed: {str(e)}"


async def run_get_news_headlines(args: dict) -> str:
    """Fetch recent headlines via Google News RSS search (no API key)."""
    query = args.get("query", "").strip()
    max_results = args.get("max_results", 5)

    if not query:
        return "Error: No news query provided."

    try:
        max_results = int(max_results)
    except Exception:
        max_results = 5
    max_results = max(1, min(max_results, 10))

    rss_url = (
        "https://news.google.com/rss/search?"
        f"q={httpx.utils.quote(query)}&hl=en-US&gl=US&ceid=US:en"
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(rss_url)
            resp.raise_for_status()
            xml_text = resp.text
    except Exception as e:
        return f"News fetch failed: {e}"

    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_text)
    except Exception as e:
        return f"News parse failed: {e}"

    items = root.findall(".//item")
    if not items:
        return f"No news found for: '{query}'"

    headlines = []
    for item in items[:max_results]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        # Google News sometimes wraps links with tracking; use the link directly.
        headlines.append(f"- {title}\n  {link}")

    return "News Headlines — " + query + "\n\n" + "\n".join(headlines)
    

 
 
# ============================================================
# START THE SERVER
#
# stdio_server() = communicate via stdin/stdout.I
# talks to this server (it runs as a subprocess).
# ============================================================
 
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )
 
if __name__ == "__main__":
    asyncio.run(main())