import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.environ["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.ai/v1",
)


# ---------------------------------------------------------
# OUR FIRST TOOL
# ---------------------------------------------------------

def search_ai_jobs(company: str):
    """
    Fake local data for now.

    The important thing in this exercise is not the search itself.
    We are testing whether Kimi decides to call a tool, receives
    its output, and then continues reasoning with that evidence.
    """

    fake_database = {
        "Logitech": [
            {
                "title": "AI Transformation Lead",
                "location": "Lausanne, Switzerland",
                "description": (
                    "Lead enterprise adoption of generative AI, "
                    "identify business use cases, support teams, "
                    "and measure business impact."
                ),
            }
        ],
        "Nestlé": [],
    }

    return {
        "company": company,
        "jobs": fake_database.get(company, []),
    }


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_ai_jobs",
            "description": (
                "Search for current AI-related job vacancies at a company. "
                "Use this when investigating whether a company shows evidence "
                "of active AI adoption, transformation, governance, or enablement."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "Company name to investigate",
                    }
                },
                "required": ["company"],
                "additionalProperties": False,
            },
        },
    }
]


messages = [
    {
        "role": "system",
        "content": (
            "You are a research agent helping identify potential "
            "GrundMind prospects. Do not assume a company has AI adoption "
            "signals. Use available tools when evidence is needed."
        ),
    },
    {
        "role": "user",
        "content": (
            "Investigate Logitech. Do we have evidence from its hiring "
            "activity that it may be actively operationalising AI?"
        ),
    },
]


# ---------------------------------------------------------
# FIRST MODEL TURN
# ---------------------------------------------------------

response = client.chat.completions.create(
    model="kimi-k2.6",
    messages=messages,
    tools=TOOLS,
    tool_choice="auto",
)

assistant_message = response.choices[0].message

messages.append(
    assistant_message.model_dump(exclude_none=True)
)


# ---------------------------------------------------------
# EXECUTE ANY TOOLS KIMI REQUESTED
# ---------------------------------------------------------

if assistant_message.tool_calls:

    for tool_call in assistant_message.tool_calls:

        print(f"\nKimi requested tool: {tool_call.function.name}")
        print(f"Arguments: {tool_call.function.arguments}")

        arguments = json.loads(tool_call.function.arguments)

        if tool_call.function.name == "search_ai_jobs":
            result = search_ai_jobs(**arguments)
        else:
            raise ValueError(
                f"Unknown tool: {tool_call.function.name}"
            )

        print("\nTool returned:")
        print(json.dumps(result, indent=2))

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result),
            }
        )


    # -----------------------------------------------------
    # SECOND MODEL TURN
    # -----------------------------------------------------

    final_response = client.chat.completions.create(
        model="kimi-k2.6",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
    )

    print("\nKimi final answer:")
    print(final_response.choices[0].message.content)

else:

    print("\nKimi did not call a tool.")
    print(assistant_message.content)
