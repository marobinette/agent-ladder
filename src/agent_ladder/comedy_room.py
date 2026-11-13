"""Two comedy writers and an originality checker share a joke board.

Run: uv run --env-file .env comedy-room
"""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import anthropic

from agent_ladder.agent import Agent
from agent_ladder.joke_board import (
    CHECKER_TOOLS,
    WRITER_TOOLS,
    JokeBoard,
    checker_handlers,
    writer_handlers,
)

TARGET_CLEARED = 5
MAX_ROUNDS = 6
CO_EDITING = True  # a joke reaches the checker only after both writers have edited it
ALTERNATE_ORDER = True
WRITER_NAMES = ("writer_a", "writer_b")
WRITER_MODEL = "claude-opus-5-5"  # cheaper while testing the machinery
CHECKER_MODEL = "claude-sonnet-5-5"
USE_STUB_CHECKER = False  # True for cheap runs with no web search
SEARCHES_PER_CHECKER_TURN = 15  # hard cap in the API; $10 per 1,000 searches

# Anthropic runs this tool server-side: no handler on our side.
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": SEARCHES_PER_CHECKER_TURN,
}

CO_EDITING_RULE = """
- Every joke is co-written. A new joke starts as a draft, and the checker only sees it after \
your partner has revised it. Your partner's drafts can't reach review without you."""

WRITER_RULES = f"""\
You share a joke board with one other writer. Together your goal is {TARGET_CLEARED} cleared jokes.

How the board works:{CO_EDITING_RULE if CO_EDITING else ""}
- Jokes waiting for review are pending until an originality checker reviews them.
- The checker clears a joke if it finds no close match on the web, or flags it if it is too similar to an existing joke.
- Any writer can revise any draft, pending, or flagged joke, including the other writer's. Cleared jokes are locked.

Each turn:
1. Call read_board first to see where things stand.
2. Make at most two changes: submit a new joke or revise an existing one. Fixing flagged jokes and \
punching up your partner's {"drafts" if CO_EDITING else "pending jokes"} come first.
3. Don't flood the board. If the jokes in play already reach {TARGET_CLEARED}, improve existing jokes \
instead of adding new ones.
4. End with a short note to your partner (one or two sentences): what you changed and any idea for them. It will be passed to them.

Write original material. Never reuse or paraphrase a known joke, including real jokes by the comedian whose style you write in."""

WRITER_A_PROMPT = f"""\
You are writer_a, a comedy writer working in the style of Jerry Seinfeld: \
Conversational and observational jokes about everyday things, \
relatable and on your side.

{WRITER_RULES}"""

WRITER_B_PROMPT = f"""\
You are writer_b, a comedy writer working in the style of Zach Galifianakis: \
deadpan delivery, awkward and uncomfortable premises, anti-humor, and non sequiturs \
that undercut the setup.

{WRITER_RULES}"""


CHECKER_PROMPT = """\
You are an originality checker for a comedy writing room. Writers submit jokes to a shared board. \
Your job is to catch jokes that already exist: published jokes, well-known bits, or close paraphrases of them. \
You review blind: you don't know who wrote each joke.

Each turn:
1. Call read_board and review every joke with status pending.
2. For each pending joke, search the web for it. Search for the distinctive premise and the punchline \
or twist, not just the topic. Use about two searches per joke, three at most.
3. Decide:
   - flag_joke if you find an existing joke with the same premise AND the same punchline or twist, \
or a close paraphrase of one. Give the URL where you found it and a one-sentence reason.
   - clear_joke otherwise. A common topic (smoke detectors, cats, airports) is not enough to flag. \
The specific comedic turn has to match.
4. Decide every pending joke this turn. Don't leave any pending.
5. End with a one-line summary per joke: ID, cleared or flagged, and why.

You can't edit jokes. "Cleared" means no close match was found, not that the joke is proven original."""


class RunLog:
    """Prints to the terminal and writes the same lines to a markdown file."""

    def __init__(self, runs_dir: Path = Path("runs")):
        runs_dir.mkdir(exist_ok=True)
        self.stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.md_path = runs_dir / f"{self.stamp}.md"
        self.json_path = runs_dir / f"{self.stamp}.json"
        self._file = self.md_path.open("w")

    def write(self, text: str = "") -> None:
        print(text)
        self._file.write(text + "\n")
        self._file.flush()  # keep the file current even if the run crashes

    def close(self) -> None:
        self._file.close()


class StubChecker:
    """Stands in for the real checker agent: no LLM, no web search.

    Flags the first pending joke it ever sees (to exercise the revise path)
    and clears every other pending joke. It has the same receive/take_turn
    interface as Agent, so the orchestrator can't tell the difference.
    """

    name = "checker"

    def __init__(self, board: JokeBoard):
        self.board = board
        self.has_flagged = False

    def receive(self, text: str) -> None:
        pass  # the stub doesn't need instructions

    def take_turn(self) -> str:
        actions = []
        for joke in list(self.board.jokes.values()):
            if joke.status != "pending":
                continue
            if not self.has_flagged:
                self.board.flag_joke(joke.id, "https://example.com/stub", "stub flag to test revision")
                self.has_flagged = True
                actions.append(f"flagged {joke.id}")
            else:
                self.board.clear_joke(joke.id)
                actions.append(f"cleared {joke.id}")
        return ", ".join(actions) if actions else "nothing pending"


def build_room(client: anthropic.Anthropic) -> tuple[JokeBoard, list[Agent], "Agent | StubChecker"]:
    board = JokeBoard(required_editors=set(WRITER_NAMES) if CO_EDITING else None)
    writers = [
        Agent(
            name=name,
            system_prompt=prompt,
            client=client,
            tools=WRITER_TOOLS,
            tool_handlers=writer_handlers(board, name),
            model=WRITER_MODEL,
        )
        for name, prompt in [("writer_a", WRITER_A_PROMPT), ("writer_b", WRITER_B_PROMPT)]
    ]
    if USE_STUB_CHECKER:
        checker = StubChecker(board)
    else:
        checker = Agent(
            name="checker",
            system_prompt=CHECKER_PROMPT,
            client=client,
            tools=CHECKER_TOOLS + [WEB_SEARCH_TOOL],
            tool_handlers=checker_handlers(board),
            model=CHECKER_MODEL,
            max_tokens=2048,  # room for searches plus a summary
        )
    return board, writers, checker


def run(board: JokeBoard, writers: list[Agent], checker, log: RunLog) -> tuple[int, list]:
    writer_a, writer_b = writers
    partner = {writer_a.name: writer_b, writer_b.name: writer_a}
    last_note: dict[str, str] = {}  # writer name -> their most recent note
    checker_traces: list[tuple[int, list]] = []  # (round, checker messages) per round

    for round_num in range(1, MAX_ROUNDS + 1):
        if ALTERNATE_ORDER and round_num % 2 == 0:
            writers = [writer_b, writer_a]
        else:
            writers = [writer_a, writer_b]
        log.write(f"\n## Round {round_num} of {MAX_ROUNDS} ({writers[0].name} first)")
    
        for writer in writers:
            other = partner[writer.name]
            prompt = (
                f"Round {round_num} of {MAX_ROUNDS}. Your turn. "
                f"Cleared so far: {board.cleared_count()}/{TARGET_CLEARED}."
            )
            note = last_note.get(other.name)
            if note:
                prompt += f"\n\nNote from {other.name}:\n{note}"
            writer.receive(prompt)
            text = writer.take_turn()
            if text.strip():
                last_note[writer.name] = text
            log.write(f"\n**[{writer.name}]** {text or '(no note)'}")

        # The checker gets no writer chat: blind review, and no lobbying.
        # It starts each round with an empty history: the board holds all the state
        # it needs, and old search results would otherwise be resent (and billed) every round.
        if isinstance(checker, Agent):
            checker.reset()
        checker.receive("Review all pending jokes.")
        log.write(f"\n**[{checker.name}]** {checker.take_turn()}")
        if isinstance(checker, Agent):
            checker_traces.append((round_num, list(checker.messages)))

        if board.cleared_count() >= TARGET_CLEARED:
            log.write(f"\nReached {TARGET_CLEARED} cleared jokes after round {round_num}.")
            return round_num, checker_traces

    log.write(f"\nStopped at the round cap with {board.cleared_count()} cleared.")
    return MAX_ROUNDS, checker_traces


def report(board: JokeBoard, log: RunLog) -> None:
    log.write("\n## Final board (checker view)\n")
    log.write(board.read_board("checker"))

    log.write("\n## Cleared jokes and who wrote each version")
    for joke in board.jokes.values():
        if joke.status != "cleared":
            continue
        editors = " -> ".join(v["editor"] for v in joke.history)
        log.write(f"\n**#{joke.id}** ({editors})\n\n> {joke.text}")


def _field(obj, name):
    """Blocks from the SDK are objects; blocks we built are dicts."""
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def write_trace(title: str, messages: list, log: RunLog) -> None:
    """Every message in one agent's history, including tool calls and results."""
    log.write(f"\n## Trace: {title}")
    for message in messages:
        content = message["content"]
        if isinstance(content, str):  # orchestrator prompt
            log.write(f"\n**-> prompt:** {content}")
            continue
        for block in content:
            kind = _field(block, "type")
            if kind == "text":
                log.write(f"\n**says:** {_field(block, 'text')}")
            elif kind in ("tool_use", "server_tool_use"):
                args = json.dumps(_field(block, "input"))
                where = " (server)" if kind == "server_tool_use" else ""
                log.write(f"\n`{_field(block, 'name')}({args})`{where}")
            elif kind == "tool_result":
                tag = " (error)" if _field(block, "is_error") else ""
                log.write(f"\n```\n{_field(block, 'content')}{tag}\n```")
            elif kind == "web_search_tool_result":
                results = _field(block, "content")
                if isinstance(results, list):
                    lines = [f"- {_field(r, 'title')} ({_field(r, 'url')})" for r in results]
                    log.write("\n" + ("\n".join(lines) if lines else "- (no results)"))
                else:  # a single error object, not a list
                    log.write(f"\n- search error: {_field(results, 'error_code')}")


def save_json(board: JokeBoard, writers: list[Agent], checker, rounds_used: int, log: RunLog) -> None:
    stub = not isinstance(checker, Agent)
    data = {
        "settings": {
            "target_cleared": TARGET_CLEARED,
            "max_rounds": MAX_ROUNDS,
            "co_editing": CO_EDITING,
            "writer_model": WRITER_MODEL,
            "checker": "stub" if stub else CHECKER_MODEL,
            "searches_per_checker_turn": None if stub else SEARCHES_PER_CHECKER_TURN,
        },
        "outcome": {
            "rounds_used": rounds_used,
            "cleared": board.cleared_count(),
            "reached_target": board.cleared_count() >= TARGET_CLEARED,
            "web_searches": 0 if stub else checker.web_searches,
        },
        "prompts": {w.name: w.system_prompt for w in writers} | ({} if stub else {"checker": CHECKER_PROMPT}),
        "jokes": [asdict(joke) for joke in board.jokes.values()],
    }
    log.json_path.write_text(json.dumps(data, indent=2))


def main():
    client = anthropic.Anthropic()
    board, writers, checker = build_room(client)
    log = RunLog()
    log.write(f"# Comedy room run {log.stamp}")
    checker_desc = "stub" if USE_STUB_CHECKER else f"{CHECKER_MODEL} with web search"
    log.write(
        f"\nWriters: {WRITER_MODEL}. Checker: {checker_desc}. "
        f"Target: {TARGET_CLEARED} cleared. Cap: {MAX_ROUNDS} rounds. Co-sign: {CO_EDITING}."
    )
    try:
        rounds_used, checker_traces = run(board, writers, checker, log)
        report(board, log)
        if isinstance(checker, Agent):
            log.write(f"\nWeb searches: {checker.web_searches} (about ${checker.web_searches * 0.01:.2f} plus tokens)")
        for writer in writers:
            write_trace(writer.name, writer.messages, log)
        for round_num, messages in checker_traces:
            write_trace(f"checker, round {round_num}", messages, log)
        save_json(board, writers, checker, rounds_used, log)
    finally:
        log.close()
    print(f"\nSaved {log.md_path} and {log.json_path}")


if __name__ == "__main__":
    main()