# comedy writer's room

Three AI agents work together to produce five original jokes. Two comedy writers draft and rewrite jokes on a shared board, and an originality checker searches the web to make sure each joke doesn't already exist.

It's a small project meant to test multi-agent collaboration: the agents are built from a hand-written agent loop, and the rules of the room live in code rather than in the prompts.

## Setup

| Agent | Role | Tools |
|---|---|---|
| `writer_a` | Comedy writer (currently Jerry Seinfeld's style; earlier runs used Mitch Hedberg) | `submit_joke`, `revise_joke`, `read_board` |
| `writer_b` | Comedy writer in Zach Galifianakis's style | `submit_joke`, `revise_joke`, `read_board` |
| `checker` | Originality checker | `clear_joke`, `flag_joke`, `read_board`, web search |

Each round, both writers take a turn, then the checker reviews everything waiting for review. The run ends when 5 jokes are cleared, or after 6 rounds.

Writers pass each other a short note at the end of every turn. The checker hears nothing from the writers.

## Rules

The rules are enforced by the board's code, so an agent can't talk its way past them.

- **Statuses.** A joke moves through `draft` → `pending` → `cleared` or `flagged`. A flagged joke goes back to `pending` when someone revises it. Cleared jokes are locked.
- **Co-editing** (`CO_EDITING`). A new joke starts as a draft. It only goes to the checker after the *other* writer has revised it, so every cleared joke has both writers in its history.
- **Anyone can revise anything** that isn't cleared, including the partner's jokes.
- **Each agent gets only its own tools.** Writers can't clear jokes, and the checker can't edit them.
- **Identity comes from the code, not the model.** The harness fills in who is calling each tool, so a writer can't claim to be someone else.
- **Blind review.** The checker doesn't see who wrote a joke, and it doesn't see drafts.
- **Limited feedback.** When a joke is flagged, writers only see "That is too much like an existing joke I found on the web." The checker's source URL is kept in the logs but hidden from the writers, so they can't read the original and drift toward it.
- **The flag standard.** The checker flags a joke only if an existing joke has the same premise *and* the same punchline or twist. A common topic isn't enough. "Cleared" means no close match was found, not that the joke is proven original.
- **Search limit.** The checker can run at most 15 web searches per turn (enforced by the API).
- **Fresh checker every round.** The checker's memory is wiped before each review. The board holds everything it needs.
- **Alternating order** (`ALTERNATE_ORDER`). The writers swap who goes first each round.

## Running it

```bash
uv run --env-file .env comedy-room     # run the room
uv run --env-file .env check-checker   # test the checker on known and new jokes
uv run joke-board                      # board tests, no API calls
```

Settings are constants at the top of `src/agent_ladder/comedy_room.py`: `TARGET_CLEARED`, `MAX_ROUNDS`, `CO_EDITING`, `ALTERNATE_ORDER`, the models, and `USE_STUB_CHECKER` (a free fake checker with no web search).

Each run writes two files to `runs/`:
- `<timestamp>.md`: a readable log with every round, the final board, and full traces of each agent's tool calls and searches
- `<timestamp>.json`: settings, outcome, prompts, and every joke with its version history

## Files

| File | What it does |
|---|---|
| `agent.py` | The `Agent` class: one model, its own message history, and the tool loop |
| `joke_board.py` | The shared board, its rules, the tool schemas, and each role's view |
| `comedy_room.py` | Builds the three agents and runs the rounds |
| `check_checker.py` | Calibrates the checker against jokes with known answers |

## Runs

**Development runs** (logs not kept)

| Run | What changed | Result |
|---|---|---|
| Stub checker ×2 | Fake checker, no co-editing | Writers never touched each other's jokes. One writer sat out turns to avoid resetting a joke's review. |
| First real checker | Web search on, no co-editing | 2 rounds, 9 searches, 0 flags. First cross-revision: writer_b rewrote a writer_a joke built on a worn-out saying. |
| Checker calibration | 4 test jokes | 4/4 correct. Flagged a famous Hedberg one-liner and a reworded version of it; cleared two new jokes, including one on the same topic. |

**Logged runs** (in `runs/`)

All three used co-editing, writer_a in Seinfeld's style, and reached 5 cleared jokes in 3 rounds with 10 searches and no flags. "Edit size" is how similar each revision is to the version before it (1.0 = unchanged, near 0 = rewritten).

| Run | Writers | Order | What happened |
|---|---|---|---|
| `2026-11-13_110036` | Sonnet | writer_a always first | writer_a drafted all 5 jokes; writer_b rewrote every one almost completely (0.05 to 0.17). The writer who edits second controls the final joke. |
| `2026-11-13_111441` | Sonnet | Alternating* | writer_b drafted the 2 jokes in the round it led, and writer_a polished them (0.64 to 0.77). writer_b still rebuilt writer_a's drafts (0.03 to 0.12). |
| `2026-11-13_111911` | Opus | Alternating* | Both writers made light edits (0.59 to 0.97), closer to polishing than rewriting. |

\* These two runs alternated, but their JSON files don't record it. The round headers in the `.md` files show the order.

Across runs, the same premises keep coming back (junk drawers, grocery stores, elevators), because each run starts from the same prompts with no memory of earlier runs.

## Example: how one joke evolved

From run `2026-11-13_110036`.

**1. The idea.** At the end of round 2, writer_a said it would try a "group-chat blunder" next. writer_b replied with an angle: replying "Who is this?" to a group chat you've been in for years.

**2. writer_a's draft** (round 3):

> I've been in my family group chat for six years, and last week I typed, "Who is this?" I don't know why. My mother replied, "It's your mother." Then my cousin wrote, "It's me, Danny." Then my uncle, who has never said anything in that chat, wrote, "We've been wondering the same about you." Now I just react to messages with a thumbs up. It's the only way I can prove I'm still alive.

writer_a's note: the uncle's line is the center of it; make it more deadpan, and find a less expected ending than the thumbs-up.

**3. writer_b's rewrite:**

> I've been in my family group chat for six years. Last week I typed, "Who is this?" and sent it before I could think. My mother wrote, "It's your mother." My cousin wrote, "It's Danny." Then my uncle, who has never said a word in that chat, wrote, "We assumed you were a bot." Nobody disagreed. Now I send a photo of a sandwich every Sunday at noon. I don't eat sandwiches. I just want them to know the bot is doing fine.

writer_b flattened the uncle's line into "We assumed you were a bot," and replaced the thumbs-up with the sandwich photo.

**4. The checker** searched twice, for the uncle's line and for the sandwich ending. It found general group-chat humor and sandwich puns, but nothing with the same turn, so it cleared the joke.

Both writers shaped this one: writer_b suggested the angle, writer_a built the joke and pointed at what to fix, and writer_b delivered the final version.

## Also in this repo

Earlier pieces from a lab skill-share talk on agent harnesses and MCP: a 20 Questions agent (`twenty_questions_harness.py`), the same game as an MCP server, and MCP servers for paper search (OpenAlex) and a reading list.