import os
import sys
import httpx2

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

mcp = MCPServer('openalex')
OPENALEX_WORKS_URL = "https://api.openalex.org/works"

try:
    OPENALEX_API_KEY = os.environ["OPENALEX_API_KEY"]
except KeyError:
    sys.exit("OPENALEX_API_KEY is not set. Run: uv run --env-file .env openalex-server")

print(f"openalex: API key loaded (...{OPENALEX_API_KEY[-4:]})", file=sys.stderr)

OPENALEX_WORKS_URL = "https://api.openalex.org/works"


@mcp.tool()
async def search_papers(query: str, limit: int = 5, from_year: int | None = None) -> dict:
    """Search OpenAlex for papers whose title or abstract matches the query.

    Results are sorted by citation count, most cited first. Use from_year to
    only include papers published in or after that year.

    Returns the total number of matches and a list of papers, each with
    title, year, and cited_by_count.
    """
    filters = [f"title_and_abstract.search:{query}"]
    if from_year is not None:
        filters.append(f"publication_year:>{from_year - 1}")

    params = {
        "filter": ",".join(filters),
        "sort": "cited_by_count:desc",
        "per_page": limit,
        "api_key": OPENALEX_API_KEY,
    }

    async with httpx2.AsyncClient(timeout=15.0) as client:
        response = await client.get(OPENALEX_WORKS_URL, params=params)
        response.raise_for_status()
        data = response.json()

    return {
        "total_matches": data["meta"]["count"],
        "papers": [trim_work(work) for work in data["results"]],
    }

def rebuild_abstract(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    pairs = [(pos, word) for word, positions in index.items() for pos in positions]
    return " ".join(word for _, word in sorted(pairs))


def trim_work(work: dict) -> dict:
    authors = [a["author"]["display_name"] for a in work["authorships"][:3]]
    if len(work["authorships"]) > 3:
        authors.append("et al.")
    source = (work.get("primary_location") or {}).get("source") or {}
    return {
        "title": work["display_name"],
        "authors": ", ".join(authors),
        "year": work["publication_year"],
        "venue": source.get("display_name"),
        "cited_by_count": work["cited_by_count"],
        "url": work["doi"] or work["id"],
        "abstract": rebuild_abstract(work["abstract_inverted_index"]),
    }

def main():
    mcp.run()