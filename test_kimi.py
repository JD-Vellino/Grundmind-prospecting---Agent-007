import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.environ["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.ai/v1",
)

response = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[
        {
            "role": "system",
            "content": "You are the reasoning engine for a B2B prospect research agent.",
        },
        {
            "role": "user",
            "content": (
                "A Swiss company is hiring an AI Adoption Lead. "
                "Explain in two sentences why this could be a useful "
                "prospecting signal for GrundMind."
            ),
        },
    ],
)

print(response.choices[0].message.content)
