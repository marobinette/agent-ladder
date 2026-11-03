import os
import sys

import httpx2
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

mcp = MCPServer("reading-list")

try:
    READING_LIST_URL = os.environ["READING_LIST_URL"].rstrip("/")
    READING_LIST_TOKEN = os.environ["READING_LIST_TOKEN"]
except KeyError as missing:
    sys.exit(f"{missing.args[0]} is not set. Run: uv run --env-file .env reading-list-server")

print("reading-list: config loaded", file=sys.stderr)


@mcp.tool()
async def add_paper(
    title: str,
    authors: str | None = None,
    year: int | None = None,
    venue: str | None = None,
    url: str | None = None,
    abstract: str | None = None,
) -> dict:
    """Add one paper to Mikey's reading list with status "to-read".

    Only title is required. When adding a paper from search_papers results,
    pass its title, authors, year, venue, url, and abstract unchanged.
    Call once per paper. Returns the id and title of the new entry.
    """
    body = {"title": title, "status": "to-read"}
    optional = {"authors": authors, "venue": venue, "url": url, "abstract": abstract}
    body.update({key: value for key, value in optional.items() if value is not None})
    if year is not None:
        body["year"] = str(year)

    async with httpx2.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{READING_LIST_URL}/api/papers",
            json=body,
            headers={"Authorization": f"Bearer {READING_LIST_TOKEN}"},
        )

    if response.status_code >= 400:
        raise ToolError(f"Reading list API returned HTTP {response.status_code}; the paper was not added.")

    created = response.json() if response.content else {}
    return {"id": created.get("id"), "title": created.get("title", title)}


def main():
    mcp.run()