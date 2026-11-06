# Core Agent Ideas

Here's the vocabulary I'd make sure the room leaves with, in the order your demos introduce it. I've kept it to terms the audience needs to follow what you show them.

### Core (cover in "Why use tools and agents?")

| Term | Definition to put on the slide |
| --- | --- |
| **Model** | Takes text in and gives text out. It can't act on the world by itself. |
| **Tool** | A capability you describe to the model with a name, a description and an input schema. **Your code** runs it, not Claude. |
| **Tool call (`tool_use`)** | The model's structured request: "call `ask_question` with these arguments." It's a request, not an action. |
| **Tool result (`tool_result`)** | What your code sends back, matched to the request by `tool_use_id`. |
| **Agent** | A model running in a loop: it decides, calls a tool, sees the result and decides again, until the task is done. |
| **Agentic loop / harness** | The code that runs that loop: it sends messages, runs tools, appends results and checks when to stop. In your cold open, `twenty_questions_harness.py` *is* the harness. |

These six answer "What just happened?" If people leave with nothing else, they should have these.

### Mechanics (cover while walking through the harness code)

| Term | Why it matters |
| --- | --- |
| **Input schema (JSON Schema)** | It's the contract between the model and your code. It tells Claude what arguments are valid. |
| **Tool description** | It works as a prompt: Claude chooses tools based on it. Your "yes or no" change is a good example. |
| **System prompt** | The rules of the game, separate from the conversation. |
| **Messages / conversation history** | The API is stateless. You resend the whole history every turn, and that's why the loop appends. |
| **`stop_reason`** | Tells you why Claude stopped: `tool_use` means "run my tool," and `end_turn` means "I'm done." The loop runs on this one value. |
| **`tool_choice`** | Lets you force or forbid tool calls. You use `none` to make Claude give its final guess. |

### Scaling up (the MCP rungs)

| Term | Definition |
| --- | --- |
| **MCP (Model Context Protocol)** | A standard way to package tools so any MCP client (Claude Code, Claude Desktop) can use them without your own loop. |
| **MCP server / client** | The server *offers* tools, as your four Python servers do. The client *connects* to it and runs the agent loop. |
| **Elicitation** | An MCP server asking the human for input mid-tool. It replaces `input()` in the server version. |
| **Composition** | Several tools from different servers used in one task. In the DP demo, the model connected `search_papers` to `add_paper` without any glue code. |

### Ideas that aren't terms but should be named

- **Separation of concerns:** Claude decides, and your code executes. This is the calendar point: the backend is your choice.
- **Guardrails live in code:** the question budget is enforced by `MAX_QUESTIONS`, not by trusting the model.
- **Judgment versus retrieval:** the API ranked papers by citations, and the model judged which ones were actually about DP.

### What I'd leave out

Workflows versus agents, RAG, embeddings, fine-tuning, multi-agent systems, server/hosted tools, and MCP resources and prompts. They're all real, but none of them appear in your demos. Each one adds a definition the room has to hold without seeing it used.

**Suggestion:** once a term has been defined, keep using the exact same word for it. For example, always say "harness" and never switch between "loop," "wrapper" and "runner." Your slide 2 already uses "wrapper" as the *wrong* answer, so contrasting it with "harness" or "agentic loop" makes the distinction stick.

Want me to turn the core six into the "Why use tools and agents?" section?

---

# From harness to server

I'd frame the transition as "most of the harness is generic plumbing, so let someone else run the loop."

### The transition

**1. Sort the harness into two piles.** Go back to `twenty_questions_harness.py` and ask the room which lines are actually about 20 questions. Highlight them in two colors:

- **Game:** the `ask_question` schema, `get_answer()`, `VALID_ANSWERS`, `MAX_QUESTIONS`.
- **Plumbing:** `send_message`, the `while` loop, `messages.append`, the `stop_reason` check, `tool_use_id` matching, `tool_choice: none`.

The plumbing is the bigger pile, and every agent needs the same plumbing.

**2. The reveal:** "Claude Code *is* a harness. What if it ran the loop and we only supplied the game?"

**3. Show the server.** It's about 25 lines of real code, and all of it is game. Then show the mapping:

| Harness | Server | Who handles it now |
| --- | --- | --- |
| `tools = [{... "input_schema" ...}]` | `def ask_question(question: str)` + description | The SDK generates the schema from type hints |
| `get_answer()` with `input()` | `Elicit(message=question, schema=Answer)` | Claude Code shows the form |
| `VALID_ANSWERS` retry loop | `Literal["yes", "no"]` | The form only allows valid answers |
| `while` loop, `messages`, `stop_reason`, `tool_use_id` | *(gone)* | Claude Code |
| `MAX_QUESTIONS` check in the loop | `ToolError` in the resolver | Still your code |
| `tool_choice: none` to force the final guess | `ToolError` text: "make your final guess" | **The model**, if it follows the instruction |
| `SYSTEM_PROMPT`, `MODEL` | *(gone)* | Whoever runs the client |

**4. Register and play live.** Run `claude mcp add ...` (or point at `.mcp.json`), then say "let's play 20 questions" in Claude Code and let the form appear. It's the same game as the cold open, with none of the plumbing.

### Points I'd make sure to call out

1. **The tool contract didn't change.** It has the same name, the same description and the same single `question` argument. Only where it runs changed. This is the payoff of "a tool is a request, not an action."
2. **Type hints become the schema.** `question: str` turns into the JSON Schema you wrote by hand in the harness. The `room` parameter is hidden from Claude because a resolver fills it in, not the model.
3. **`Elicit` replaces `input()`.** A stdio server can't read from a keyboard because stdin is the protocol pipe, so it asks the client to ask the human.
4. **The resolver runs before the tool body and may run more than once.** That's why the counter is incremented in `ask_question` and not in `ask_the_room`. It's a small detail, but it shows that a framework running your code brings rules of its own.
5. **Errors are messages to the model.** The `ToolError` text is written for Claude, telling it to stop and guess. This is a good place to repeat "tool descriptions are prompts."
6. **You gave up some control.** Point at the `tool_choice` row in the table. The harness *guaranteed* a final guess, while the server only *asks* for one. You also no longer choose the model or the system prompt. Less code means less control, and that tradeoff is the honest center of this rung.
7. **It's reusable.** Any MCP client that supports elicitation can play, whichever model drives it. Your simpler tool-only servers work in almost any client. The harness only ever worked in your terminal.

### Two gotchas to check before the talk

- **The question counter never resets.** `questions_asked` is a global that lasts as long as the server process, and Claude Code keeps that process running for the whole session. A second game in the same session starts with the questions already used. Either restart the session between games or accept the quirk; it could even be a teaching moment about server state.
- **Claude may ask in chat instead of using the tool.** Claude Code can already talk to you, so a vague prompt might not trigger the tool. Say "Let's play 20 questions using the ask_question tool," and rehearse it once.

Want me to build this as slides? I'd make one for the two-color harness, one for the server code and one for the mapping table.

---

# Key MCP concepts

Focus on **tools**, and only name **resources** and **prompts**. Two concepts outside that trio matter more for your talk: **how the pieces connect** and **elicitation**.

The docs are right that tools, resources and prompts are the three things a server can offer. But every one of your demos uses tools only. Concepts you can't show will be the first ones people forget.

### What to teach, in order

**1. Host, client, server: who talks to whom**
- **Host:** the app the user works in, here Claude Code.
- **Client:** the connection inside the host. There's one per server.
- **Server:** your Python process, which offers capabilities.

This answers "where does the loop live now?" for the harness-to-server step: in the host.

**2. Transport: stdio**

Claude Code starts your server using the command in `.mcp.json` and talks to it over stdin and stdout. That one fact explains both the `uv run ...` registration and why `Elicit` has to replace `input()`. It's worth a sentence, not a slide.

**3. Tools: the main event**

All four of your servers are about tools, so this is where your time should go. You've already covered most of it: the contract, the generated schema, `ToolError`, and composing tools across servers.

**4. Elicitation: the server asking the user**

Your 20 questions server depends on it. It's technically a *client* feature (something the client provides to servers), which is why it isn't in the docs' "core three." Pair it with the caveat that not every client supports it.

**5. Resources and prompts: one slide, defined by who's in control**

| Primitive | Who decides to use it | Example in your repo, if you built it |
| --- | --- | --- |
| **Tool** | The **model** | `search_papers`, `add_paper`, `ask_question` |
| **Resource** | The **application/user** attaches it as context | The reading list exposed as `readinglist://papers` for the model to read |
| **Prompt** | The **user** picks it, like a slash command | `/find-papers <topic>`, a template for the DP task |

The control column is the useful idea. It separates the three primitives better than definitions alone, and it ties back to your theme of who decides what.

### What I'd skip

- **Sampling and roots.** These are client features too, but the installed SDK marks both as deprecated in the 2026-07-28 protocol, and neither appears in your demos.
- **Protocol details** such as JSON-RPC, capability negotiation messages and the newer request/response round trip behind `Resolve`. Mention capability negotiation in one line at most, when you explain why elicitation doesn't work everywhere.

This refines the earlier advice to leave out MCP resources and prompts. Since the docs call them core, the audience may expect them, so name them on one slide with the control framing, but don't demo them.

---

# How the server actually runs: two phases

The confusing part of `twenty_questions_server.py` is that code runs where you can't see it. It isn't running inside your `def`; it's running in the **SDK**, which *reads* your function signature and acts on it.

### Phase 1: Startup (once, when the server starts)
1. Imports and constants load.
2. Python reaches `@mcp.tool(...)`. The decorator receives `ask_question` and **reads its signature**. It builds the schema from `question: str`, sees that `room` is marked `Resolve(ask_the_room)`, and stores all of that. **Nothing is called.** No question exists yet.
3. `main()` → `mcp.run()`. The server waits. Nothing in your code runs after this line; from here the SDK calls your functions when messages arrive.

### Phase 2: Each tool call (much later, once per question)
4. Claude Code asks for the tool list, and the SDK sends the stored schema. That's how Claude knows to provide a `question`.
5. Claude sends `ask_question(question="Is it alive?")`.
6. The SDK calls `ask_the_room(question="Is it alive?")`, matching the parameter **by name** to the tool argument. It returns an `Elicit`.
7. Claude Code shows the form, the room answers, and the SDK builds `Answer(answer="yes")`.
8. The SDK calls `ask_question(question=..., room=...)`, and the **body** runs: the counter goes up and `"yes"` goes back to Claude as the `tool_result`.

### What the SDK does for you, written out
```python
# Phase 1, startup: the decorator does this
TOOLS["ask_question"] = {
    "function": ask_question,
    "schema": {"question": "string"},       # from `question: str`
    "resolvers": {"room": ask_the_room},    # from `Resolve(ask_the_room)`
}

# Phase 2, when Claude calls the tool
def handle_tool_call(name, args):           # args = {"question": "Is it alive?"}
    tool = TOOLS[name]
    request = tool["resolvers"]["room"](question=args["question"])   # ask_the_room
    reply = ask_user_through_client(request)                          # the form
    return tool["function"](question=args["question"], room=reply)   # the body
```
Everything that feels hidden lives in `handle_tool_call`, inside the SDK.

### Supporting facts
- **Tool arguments are the tool function's plain parameters.** `question: str` is a tool argument. `room` (marked `Resolve`) and any `Context` parameter are left out of the schema and filled in by the SDK.
- **Resolver parameters are matched by name.** `ask_the_room(question)` gets the tool argument called `question`. Rename it to `q` and the server fails **at startup** with `InvalidSignature: Resolver 'ask_the_room' parameter 'q' cannot be resolved` (tested).
- **`Annotated` is standard Python.** `Annotated[Answer, Resolve(ask_the_room)]` means "type `Answer`, plus a note for the SDK: get it by running `ask_the_room`." Python ignores the note; the SDK reads it. FastAPI uses the same pattern.
- **The `room` argument is the room's answer, not the room.** The tool is `ask_question`; the room is the outside world it reaches. Renaming `room` to `reply` would make that clearer.
- **The body** is the indented code after the signature. The limit check sits in the resolver so it runs *before* the room is asked; the counter sits in the body because the body runs exactly once per call.

### One sentence for the slide
**"Your function signature is instructions for the SDK. The SDK reads it at startup, then runs the steps it describes each time Claude calls the tool."**

The harness is **imperative**: every step is a line you wrote. The server is **declarative**: you describe what you need, and the framework decides how and when to run it.

---

# Agent vs. harness vs. tool

### Definitions
- **Agent:** the behavior. In Anthropic's words, agents are "systems where LLMs dynamically direct their own processes and tool usage." In practice they're "typically just LLMs using tools based on environmental feedback in a loop." The test is **who decides the next step**: if Claude does, it's an agent.
- **Workflow:** the contrast. LLMs and tools follow code paths **you** fixed in advance, for example "ask 3 questions, then guess."
- **Harness:** the code around the model that makes the agent possible. It sends the conversation, runs tools, appends results, checks `stop_reason` and handles context and permissions. It runs the loop but doesn't decide. "Harness" is an informal term with no formal spec. Anthropic calls Claude Code's core "the agent harness."
- **Tool (server):** a capability the agent can call. It doesn't call a model, run a loop or decide anything.
- **Agent = model + harness + tools.** The harness is the part you write; the model is the part that decides.

### The files in this repo

| File | Kind | Calls a model? | Runs the loop? | Who decides the next step? | Talks to | Tool(s) |
| --- | --- | --- | --- | --- | --- | --- |
| `twenty_questions_harness.py` | **Harness** (plus Claude, it's an agent) | Yes, `messages.create` | Yes, `while` + `stop_reason` | Claude | Claude API + the room via `input()` | `ask_question`, defined as a dict |
| `twenty_questions_server.py` | **Tool server** | No | No | Claude, via whatever harness runs it | The room, via `Elicit` | `ask_question` |
| `openalex_server.py` | **Tool server** | No | No | Claude, via whatever harness runs it | OpenAlex API (GET) | `search_papers` |
| `reading_list_server.py` | **Tool server** | No | No | Claude, via whatever harness runs it | Reading list API (POST) | `add_paper` |

In the MCP setup, **Claude Code takes the place of `twenty_questions_harness.py`**, and the three servers plug into it. Claude Code is a production harness: the same `while stop_reason == "tool_use"` loop plus permissions, context management, many tools and a UI.

### Where the agent shows up
In the DP demo, neither server knows the other exists. Claude called `search_papers`, **judged** which results were really about DP, then called `add_paper` twice. Claude made those choices and Claude Code ran the loop around them. The intelligence lives in the loop, not in the servers.

### Control: two different kinds
Building agents involves two kinds of control:

1. **Control over decisions** (what to ask, when to guess). Claude keeps this in every agent setup. Across approaches, the more the model decides, the less of this you have: plain code > workflow > agent. Agents trade this control for flexibility.
2. **Control over the loop and its rules.** This depends on **who owns the harness**. Writing your own harness gives you the most control you can have over an agent.

| Setup | You control | Someone else controls |
| --- | --- | --- |
| **Your harness** | Model, system prompt, max turns, `tool_choice`, what goes into `messages`, when to stop, how the room answers | Only Claude's choices within the rules you set |
| **MCP server + Claude Code** | The tool itself: its description, schema, `ToolError` text and guardrails | Model, system prompt, loop, stop condition, context. Claude Code decides all of these. |

In the harness, code enforces the rules:
- the question count: the `while questions_asked < MAX_QUESTIONS` loop
- a guaranteed final guess: `tool_choice: none`
- input validation: the `get_answer` retry loop

In the server version, the most you can do is send a message asking Claude to stop.

The tradeoff in the harness-to-server step:
- **Own the harness:** most control and most code, and it only runs in your terminal.
- **Plug into a harness:** least code and reuse in any MCP client, but you give up the loop.

Your harness is still an agent, because Claude chooses the questions and when to guess. It sits at the controlled end of the agent side.

### Lines for the slides
- "An agent is Claude choosing its next step in a loop. The harness is the code that runs that loop. We built a tiny one; Claude Code is a big one."
- "MCP lets us plug our tool into someone else's harness instead of maintaining our own."
- "Writing your own harness gives you the most control over the agent. Using an MCP server trades that control for less code and reuse."
- "MCP is a protocol, like HTTP. The `mcp` package is the Python SDK that speaks it, the way Flask speaks HTTP."

### References
- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) (Anthropic, Dec 2024): the agent definition and the agent-vs-workflow distinction.
- [Building agents with the Claude Agent SDK](https://anthropic.com/engineering/building-agents-with-the-claude-agent-sdk) (Anthropic): calls Claude Code's core "the agent harness."
