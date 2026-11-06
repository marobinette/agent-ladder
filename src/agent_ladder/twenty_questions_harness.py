# usage: uv run --env-file .env twenty-questions-harness
import anthropic

client = anthropic.Anthropic()
MODEL = "claude-opus-5-5"
INPUT_PRICE = 4 / 1_000_000    # $ per input token (Opus 5.5)
OUTPUT_PRICE = 20 / 1_000_000  # $ per output token (Opus 5.5)
MAX_QUESTIONS = 20
VALID_ANSWERS = {"yes", "no"}

SYSTEM_PROMPT = (
    "You are playing 20 Questions. A room of people has chosen a secret "
    "person, place, or thing. Use the ask_question tool for each question, "
    f"including guesses. You have {MAX_QUESTIONS} questions. Once a guess is "
    "confirmed, stop asking and announce the answer."
)

def main():
    play_game()

def send_message(model, messages, tools, system, tool_choice=None, max_tokens=1024):
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        tools=tools,
        tool_choice=tool_choice or {"type": "auto"},
    )

    return message


def print_block_text(message):
    for block in message.content:
        if block.type == "text":
            print(block.text)


def print_cost(response, total_cost):
    usage = response.usage
    cost = usage.input_tokens * INPUT_PRICE + usage.output_tokens * OUTPUT_PRICE
    total_cost += cost
    print(
        f"[cost: {usage.input_tokens} in / {usage.output_tokens} out "
        f"= ${cost:.4f} | total ${total_cost:.4f}]"
    )
    return total_cost


def get_answer(question):
    while True:
        answer = input(f"{question} (yes/no): ").strip().lower()
        if answer in VALID_ANSWERS:
            return answer
        print("Please answer yes or no.")


tools = [
    {
        "name": "ask_question",
        "description": (
            "Ask a yes-or-no question that helps you deduce the secret identity "
            "of a person, place, or thing. The room answers with exactly one of: "
            f"'yes' or 'no'. You get {MAX_QUESTIONS} questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "A yes-or-no question, e.g. Is it alive?",
                }
            },
            "required": ["question"],
        },
    }
]


def play_game():
    messages = [
        {
            "role": "user",
            "content": "The room has chosen. Ask your first question.",
        }
    ]
    questions_asked = 0
    total_cost = 0

    while questions_asked < MAX_QUESTIONS:
        response = send_message(
            model=MODEL, messages=messages, tools=tools, system=SYSTEM_PROMPT
        )
        total_cost = print_cost(response, total_cost)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            print("Stopped because:", response.stop_reason)
            return

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if questions_asked >= MAX_QUESTIONS:
                answer = "You are out of questions."
            else:
                questions_asked += 1
                print(f"[Question {questions_asked}/{MAX_QUESTIONS}]")
                answer = get_answer(block.input["question"])
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": answer}
            )
        messages.append({"role": "user", "content": tool_results})


    messages[-1]["content"].append(
        {
            "type": "text",
            "text": f"You have used all {MAX_QUESTIONS} questions. Make your final guess.",
        }
    )
    response = send_message(
        model=MODEL,
        messages=messages,
        tools=tools,
        system=SYSTEM_PROMPT,
        tool_choice={"type": "none"},
    )
    print_cost(response, total_cost)
    print_block_text(response)


if __name__ == "__main__":
    main()