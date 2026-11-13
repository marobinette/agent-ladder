import anthropic

class ToolError(Exception):
    pass

class Agent:
    def __init__(
            self,
            name: str,
            system_prompt: str,
            client: anthropic.Anthropic,
            tools: list | None = None,
            tool_handlers: dict | None = None,
            max_tokens: int = 1024,
            model: str = "claude-opus-5-5",
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.client = client
        self.tools = tools or []
        self.tool_handlers = tool_handlers or {}
        self.max_tokens = max_tokens
        self.model = model
        self.messages = []
        self.web_searches = 0

    def receive(self, text: str):
        self.messages.append(
            {
                "role": "user",
                "content": text
            }
        )

    def reset(self) -> None:
        """Forget the conversation. Tools, prompt and counters stay."""
        self.messages = []

    def join_block_text(self, response) -> str:
        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text
        return text

    def _call_model(self):
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": self.system_prompt,
            "messages": self.messages,
        }
        if self.tools:
            kwargs["tools"] = self.tools

        response = self.client.messages.create(**kwargs)

        server_use = getattr(response.usage, "server_tool_use", None)
        if server_use is not None:
            self.web_searches += server_use.web_search_requests or 0

        return response
         
    def take_turn(self) -> str:
        response = self._call_model()

        self.messages.append(
            {
                "role": "assistant",
                "content": response.content
            }
        )

        while response.stop_reason in ("tool_use", "pause_turn"):
            if response.stop_reason == "pause_turn":
                response = self._call_model()
                self.messages.append({"role": "assistant", "content": response.content})
                continue
            results = []

            for block in response.content:
                if block.type == "tool_use":
                    handler = self.tool_handlers.get(block.name)
                    if handler is None:
                        results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": f"No handler for tool: {block.name}",
                                "is_error": True,
                            }
                        )
                    else:
                        is_error = False
                        try:
                            result = handler(**block.input)
                        except ToolError as e:
                            result = str(e)
                            is_error = True
                        results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": str(result),
                                "is_error": is_error
                            }
                        )
            self.messages.append({"role": "user", "content": results})
            response = self._call_model()
            self.messages.append({"role": "assistant", "content": response.content})
        return self.join_block_text(response)

def main():
    from datetime import datetime
    from pprint import pprint

    def get_time() -> str:
        return datetime.now().isoformat()

    tools = [
        {
            "name": "get_time",
            "description": "Returns the current local time in ISO 8601 format.",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]

    client = anthropic.Anthropic()
    agent = Agent(
        name="tester",
        system_prompt="You are terse.",
        client=client,
        tools=tools,
        tool_handlers={},
    )

    agent.receive("What time is it?")
    print(agent.take_turn())
    print("---")
    pprint(agent.messages)

if __name__ == "__main__":
    main()