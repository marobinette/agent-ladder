import anthropic

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

    def receive(self, text: str):
        self.messages.append(
            {
                "role": "user",
                "content": text
            }
        )

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

        return response
         
    def take_turn(self) -> str:
        response = self._call_model()

        self.messages.append(
            {
                "role": "assistant",
                "content": response.content
            }
        )

        while response.stop_reason == "tool_use":
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    handler = self.tool_handlers.get(block.name)
                    if handler is NotImplemented:
                        results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": f"No handler for tool: {block.name}",
                                "is_error": True,
                            }
                        )
                    else:
                        result = handler(**block.input)
                        results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": str(result)
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
        tool_handlers={"get_time": get_time},
    )

    agent.receive("What time is it?")
    print(agent.take_turn())
    print("---")
    pprint(agent.messages)

if __name__ == "__main__":
    main()