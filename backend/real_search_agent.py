import json
import os

from dotenv import load_dotenv
from openai import OpenAI



load_dotenv()

client = OpenAI(
    api_key=os.environ["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.ai/v1",
)


TOOLS = [
    {
        "type": "builtin_function",
        "function": {
            "name": "$web_search",
        },
    }
]


messages = [
    {
        "role": "system",
        "content": (
            "You are a research agent for GrundMind. "
            "Your job is to investigate public evidence of enterprise AI adoption. "
            "Do not invent job vacancies, programmes, dates, or company activity. "
            "Use the available web search tool for current evidence. "
            "For this task, perform at most ONE web search. "
            "After receiving the search results, produce a final evidence report. "
            "Do not request or propose another search. "
            "If the available evidence is insufficient, explicitly say so. "
            "Clearly distinguish evidence from inference."
        ),
    },
    {
        "role": "user",
        "content": (
            "Investigate Logitech for current or recent public evidence that it "
            "is hiring for AI adoption, AI transformation, GenAI, AI enablement, "
            "AI governance, Copilot, or closely related roles. "
            "Use one web search only. "
            "Report any job title, location, evidence, and source available. "
            "If the evidence is insufficient, say so."
        ),
    },
]


while True:

    response = client.chat.completions.create(
        model="kimi-k2.6",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        response_format={"type": "json_object"},
        max_tokens=4096,
        timeout=120,
        extra_body={
            "thinking": {"type": "disabled"}
        },
    )
    

    choice = response.choices[0]

    print(f"Finish reason: {choice.finish_reason}", flush=True)
    print(f"Completion tokens: {response.usage.completion_tokens}", flush=True)

    if choice.finish_reason != "tool_calls":
        print("\nKimi final answer:\n")
        print(choice.message.content)
        break

    # Preserve Kimi's full assistant message, including tool-call state.
    messages.append(choice.message)

    for tool_call in choice.message.tool_calls:

        print(f"\nKimi requested tool: {tool_call.function.name}")

        arguments = json.loads(tool_call.function.arguments)

        query = arguments.get("query")
        if query:
            print(f"Search query: {query}")

        search_tokens = (
            arguments.get("usage", {})
            .get("total_tokens")
        )
        if search_tokens:
            print(f"Search-result tokens: {search_tokens}")

        if tool_call.function.name == "$web_search":
            # Kimi's built-in search is special:
            # we return its generated arguments unchanged.
            tool_result = arguments
        else:
            raise ValueError(
                f"Unknown tool: {tool_call.function.name}"
            )

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.function.name,
                "content": json.dumps(tool_result),
            }
        )
