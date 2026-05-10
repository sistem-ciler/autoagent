from .web_search import web_search
from .web_fetch import web_fetch

TOOLS = [
    {
        "name": "web_search",
        "description": (
            "Search the internet for current information. Use this to research topics, "
            "find competitor pricing, discover market trends, look up recent news, or find "
            "any information that may have changed since your training cutoff."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query. Use specific keywords for best results.",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (1-10). Default 5.",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": (
            "Fetch and read the full content of a webpage. Use after web_search to read "
            "articles, competitor pages, pricing pages, documentation, or any URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL to fetch (must start with http:// or https://).",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return (default 4000).",
                    "default": 4000,
                },
            },
            "required": ["url"],
        },
    },
]


def execute_tool(name: str, input_data: dict) -> str:
    if name == "web_search":
        return web_search(input_data["query"], input_data.get("num_results", 5))
    if name == "web_fetch":
        return web_fetch(input_data["url"], input_data.get("max_chars", 4000))
    return f"Unknown tool: {name}"
