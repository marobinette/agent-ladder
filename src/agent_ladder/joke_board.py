from dataclasses import dataclass, field
from functools import partial

from agent_ladder.agent import ToolError

FLAG_FEEDBACK = "That is too much like an existing joke I found on the web."
VIEWERS = ("writer", "checker")


@dataclass
class Joke:
    id: int
    author: str
    text: str
    # draft -> pending once all required editors have touched it (co-sign rule)
    # pending -> cleared | flagged; flagged -> pending on revise
    status: str = "pending"
    source_url: str | None = None
    reason: str | None = None
    history: list[dict] = field(default_factory=list)  # text versions: {"editor", "text"}


class JokeBoard:
    def __init__(self, required_editors: set[str] | None = None):
        # Co-sign rule: if set, a joke stays a draft (invisible to the checker)
        # until every name here appears in its history. None turns the rule off.
        self.required_editors = required_editors
        self.jokes: dict[int, Joke] = {}
        self.next_id: int = 1

    # --- writer tools ---

    def submit_joke(self, author: str, text: str) -> str:
        if not text.strip():
            raise ToolError("Joke text cannot be empty.")
        joke_id = self.next_id
        joke = Joke(id=joke_id, author=author, text=text)
        joke.history.append({"editor": author, "text": text})
        joke.status = self._status_after_edit(joke)
        self.jokes[joke_id] = joke
        self.next_id += 1
        return f"Joke submitted with ID {joke_id}; {self._status_message(joke)}"

    def revise_joke(self, editor: str, joke_id: int, text: str) -> str:
        joke = self._get_joke(joke_id)
        if joke.status == "cleared":
            raise ToolError(f"Joke {joke_id} is cleared; it cannot be revised.")
        if not text.strip():
            raise ToolError("The revised text cannot be empty.")
        joke.text = text
        joke.history.append({"editor": editor, "text": text})
        joke.source_url = None
        joke.reason = None
        joke.status = self._status_after_edit(joke)
        return f"Joke {joke_id} revised; {self._status_message(joke)}"

    # --- checker tools ---

    def clear_joke(self, joke_id: int) -> str:
        joke = self._get_joke(joke_id)
        if joke.status != "pending":
            raise ToolError(f"Joke {joke_id} is {joke.status}; only pending jokes can be cleared.")
        joke.status = "cleared"
        return f"Joke {joke_id} cleared."

    def flag_joke(self, joke_id: int, source_url: str, reason: str) -> str:
        joke = self._get_joke(joke_id)
        if joke.status != "pending":
            raise ToolError(f"Joke {joke_id} is {joke.status}; only pending jokes can be flagged.")
        if not source_url.strip():
            raise ToolError("A source URL is required to flag a joke.")
        joke.status = "flagged"
        joke.source_url = source_url
        joke.reason = reason
        return f"Joke {joke_id} flagged."

    # --- shared tool ---

    def read_board(self, viewer: str) -> str:
        # viewer is bound by the harness, never chosen by the model,
        # so a bad value is a bug in our code: ValueError, not ToolError.
        if viewer not in VIEWERS:
            raise ValueError(f"Unknown viewer: {viewer!r}")
        # Drafts aren't ready for review, so the checker doesn't see them.
        visible = [
            joke for joke in self.jokes.values()
            if viewer == "writer" or joke.status != "draft"
        ]
        if not visible:
            return "No jokes on the board."
        return "\n".join(self._format_joke(joke, viewer) for joke in visible)

    # --- for the orchestrator (not tools) ---

    def cleared_count(self) -> int:
        return sum(1 for joke in self.jokes.values() if joke.status == "cleared")

    # --- helpers ---

    def _get_joke(self, joke_id: int) -> Joke:
        joke = self.jokes.get(joke_id)
        if joke is None:
            raise ToolError(f"No joke with ID {joke_id}.")
        return joke

    def _missing_editors(self, joke: Joke) -> list[str]:
        if self.required_editors is None:
            return []
        editors = {version["editor"] for version in joke.history}
        return sorted(self.required_editors - editors)

    def _status_after_edit(self, joke: Joke) -> str:
        return "draft" if self._missing_editors(joke) else "pending"

    def _status_message(self, joke: Joke) -> str:
        if joke.status == "draft":
            needed = " and ".join(self._missing_editors(joke))
            return f"it is a draft and goes to review after {needed} revises it."
        return "now pending review."

    def _format_joke(self, joke: Joke, viewer: str) -> str:
        # Allowlist: each role sees only the fields named here.
        parts = [f"ID: {joke.id}"]
        if viewer == "writer":
            parts.append(f"Author: {joke.author}")  # checker reviews blind
        parts.append(f"Status: {joke.status}")
        parts.append(f"Text: {joke.text}")
        if joke.status == "draft" and viewer == "writer":
            parts.append(f"Needs edit from: {', '.join(self._missing_editors(joke))}")
        if joke.status == "flagged":
            if viewer == "writer":
                parts.append(f"Feedback: {FLAG_FEEDBACK}")
            else:
                parts.append(f"Source: {joke.source_url}")
                parts.append(f"Reason: {joke.reason}")
        return " | ".join(parts)


# --- tool schemas (what the model sees) ---

READ_BOARD_SCHEMA = {
    "name": "read_board",
    "description": "Show every joke on the shared board with its ID and status.",
    "input_schema": {"type": "object", "properties": {}},
}

WRITER_TOOLS = [
    {
        "name": "submit_joke",
        "description": "Submit a new joke to the board. Returns its ID and whether it is a draft or pending review.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "The full joke."}},
            "required": ["text"],
        },
    },
    {
        "name": "revise_joke",
        "description": "Replace the text of any draft, pending, or flagged joke, including one another writer submitted. Returns the joke's new status. Cleared jokes cannot be revised.",
        "input_schema": {
            "type": "object",
            "properties": {
                "joke_id": {"type": "integer"},
                "text": {"type": "string", "description": "The full revised joke."},
            },
            "required": ["joke_id", "text"],
        },
    },
    READ_BOARD_SCHEMA,
]

CHECKER_TOOLS = [
    {
        "name": "clear_joke",
        "description": "Mark a pending joke as cleared: you found no close match on the web.",
        "input_schema": {
            "type": "object",
            "properties": {"joke_id": {"type": "integer"}},
            "required": ["joke_id"],
        },
    },
    {
        "name": "flag_joke",
        "description": "Mark a pending joke as too similar to an existing joke. Requires the URL where you found the similar joke.",
        "input_schema": {
            "type": "object",
            "properties": {
                "joke_id": {"type": "integer"},
                "source_url": {"type": "string"},
                "reason": {"type": "string", "description": "What makes it too similar."},
            },
            "required": ["joke_id", "source_url", "reason"],
        },
    },
    READ_BOARD_SCHEMA,
]


# --- handler tables: identity is bound here, never supplied by the model ---

def writer_handlers(board: JokeBoard, name: str) -> dict:
    return {
        "submit_joke": partial(board.submit_joke, author=name),
        "revise_joke": partial(board.revise_joke, editor=name),
        "read_board": partial(board.read_board, viewer="writer"),
    }


def checker_handlers(board: JokeBoard) -> dict:
    return {
        "clear_joke": board.clear_joke,
        "flag_joke": board.flag_joke,
        "read_board": partial(board.read_board, viewer="checker"),
    }


def main():
    board = JokeBoard()
    a = writer_handlers(board, "writer_a")
    b = writer_handlers(board, "writer_b")
    checker = checker_handlers(board)

    def attempt(label, call):
        try:
            print(f"{label}: {call()}")
        except ToolError as e:
            print(f"{label}: ERROR: {e}")

    # Calls use keyword args only, the same way take_turn calls handler(**block.input).
    print("== empty board ==")
    print(a["read_board"]())

    print("\n== submit ==")
    attempt("A submits", lambda: a["submit_joke"](text="I used to be indecisive. Now I'm not sure."))
    attempt("B submits", lambda: b["submit_joke"](text="I bought a ceiling fan. Now I'm a fan of ceilings."))
    attempt("B submits blank", lambda: b["submit_joke"](text="   "))

    print("\n== checker ==")
    attempt("clear 1", lambda: checker["clear_joke"](joke_id=1))
    attempt("clear 1 again", lambda: checker["clear_joke"](joke_id=1))
    attempt("flag 99", lambda: checker["flag_joke"](joke_id=99, source_url="x", reason="y"))
    attempt("flag 2 blank url", lambda: checker["flag_joke"](joke_id=2, source_url="  ", reason="y"))
    attempt("flag 2", lambda: checker["flag_joke"](joke_id=2, source_url="https://example.com", reason="same punchline"))

    print("\n== writer view ==")
    print(a["read_board"]())
    print("\n== checker view ==")
    print(checker["read_board"]())

    print("\n== revise ==")
    attempt("A revises B's joke 2", lambda: a["revise_joke"](joke_id=2, text="My ceiling fan has more followers than I do."))
    attempt("B revises cleared 1", lambda: b["revise_joke"](joke_id=1, text="nope"))
    attempt("B revises 2 blank", lambda: b["revise_joke"](joke_id=2, text="   "))

    print("\n== after revise (checker view) ==")
    print(checker["read_board"]())
    print("\n== joke 2 history ==")
    for version in board.jokes[2].history:
        print(version)

    print(f"\ncleared: {board.cleared_count()}")

    print("\n== co-sign rule ==")
    board = JokeBoard(required_editors={"writer_a", "writer_b"})
    a = writer_handlers(board, "writer_a")
    b = writer_handlers(board, "writer_b")
    checker = checker_handlers(board)
    attempt("A submits", lambda: a["submit_joke"](text="My shadow follows me everywhere, but never helps carry anything."))
    attempt("A revises own draft", lambda: a["revise_joke"](joke_id=1, text="My shadow follows me everywhere and has never once offered to carry a bag."))
    attempt("checker clears draft", lambda: checker["clear_joke"](joke_id=1))
    print("writer view:\n" + a["read_board"]())
    print("checker view: " + checker["read_board"]())
    attempt("B revises A's draft", lambda: b["revise_joke"](joke_id=1, text="My shadow follows me everywhere and has never once offered to carry a bag. It just watches."))
    print("checker view: " + checker["read_board"]())
    attempt("checker clears", lambda: checker["clear_joke"](joke_id=1))
    print("editors:", [v["editor"] for v in board.jokes[1].history])

    print("\n== bad viewer (harness bug, should raise ValueError) ==")
    try:
        board.read_board("editor")
    except ValueError as e:
        print(f"ValueError: {e}")


if __name__ == "__main__":
    main()