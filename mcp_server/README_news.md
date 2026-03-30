# MCP news/alerts tool

**Description:** Adds a `get_news_headlines` tool that fetches top RSS headlines via Google News RSS search (no API key required). It returns up to 5 recent headlines with titles and URLs.

**Usage example (LLM prompt hint):**
- "Give me the latest tech news"
- "Show top headlines about Nepal politics"

**Tool schema:**
```json
{
  "name": "get_news_headlines",
  "description": "Fetch top recent news headlines for a given query (Google News RSS).",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "Search topic, e.g., 'Nepal politics'"},
      "max_results": {"type": "integer", "description": "Number of headlines (1-10).", "default": 5}
    },
    "required": ["query"]
  }
}
```

**Implementation notes:**
- Uses `httpx` (already a dependency) and Python stdlib `xml.etree.ElementTree` for simple RSS parsing.
- Clamps `max_results` between 1 and 10.
- Returns a compact, LLM-friendly text summary.
