"""
claude mcp add registers a new MCP server.
--scope project writes the config to .mcp.json in the repo, so it’s shared through git. Flags like this have to come before the server name.
twenty-questions is the name Claude Code shows for the server, for example in /mcp.
-- marks the end of Claude’s own options. Everything after it is the command Claude Code runs to start your server.
uv run twenty-questions-server is the same command you just tested by hand.

register: claude mcp add --scope project twenty-questions -- uv run twenty-questions-server

"""
from typing import Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel

mcp = MCPServer("twenty-questions")
MAX_QUESTIONS = 20
QUESTIONS_ASKED = 0


class Answer(BaseModel):
    answer: Literal["yes", "no", "sometimes"]

@mcp.tool(
    description=(
        "Ask a yes-or-no question that helps you deduce the secret identity of a "
        "person, place, or thing. The room answers with exactly one of: 'yes', "
        f"'no', or 'sometimes'. You get {MAX_QUESTIONS} questions."
    )
)
async def ask_question(question: str, ctx: Context) -> str:
    global questions_asked
    if questions_asked >= MAX_QUESTIONS:
        raise ToolError(
            f"You have used all {MAX_QUESTIONS} questions. Do not call "
            "ask_question again. Make your final guess in plain text instead."
        )
    questions_asked += 1

    result = await ctx.elicit(message=question, schema=Answer)
    if result.action == "accept":
        return result.data.answer
    if result.action == "decline":
        questions_asked -= 1
        return (
            "The room declined to answer. That question did not count. "
            "Ask a different question."
        )
    return "The room cancelled the game. Stop asking questions."


def main():
    mcp.run()


if __name__ == "__main__":
    main()
