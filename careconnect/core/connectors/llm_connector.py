import os
from typing import List, Optional, Dict
from openai import OpenAI

# Base URL for your Databricks serving endpoint
_BASE_URL = "https://dbc-65fcd381-2e74.cloud.databricks.com/serving-endpoints"

def _get_client() -> OpenAI:
    """
    Retrieve an authenticated OpenAI client against the Databricks LLM endpoint.
    """
    token = os.getenv("DATABRICKS_TOKEN")
    if not token:
        raise EnvironmentError("Environment variable DATABRICKS_TOKEN is not set")
    return OpenAI(api_key=token, base_url=_BASE_URL)

def chat_completion_sync(
    prompt: str,
    *,
    model: str = "databricks-llama-4-maverick",
    temperature: float = 0.7,
    system_prompt: Optional[str] = None,
    history: Optional[List[str]] = None,
) -> str:
    """
    Send a chat completion request to the Databricks LLM endpoint asynchronously,
    with optional system prompt and conversation history.

    Args:
        prompt: The new user prompt to send.
        model: The model name to use.
        temperature: Sampling temperature.
        system_prompt: Optional system-level instruction.
        history: Optional list of prior user messages (for simple history tracking).

    Returns:
        The assistant's reply.
    """
    client = _get_client()
    # Build the messages list in the order: system -> history -> new prompt
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        messages.extend([{"role": "user", "content": m} for m in history])
    messages.append({"role": "user", "content": prompt})

    # Call the async completion endpoint
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content


if __name__ == "__main__":
    import asyncio

    async def main():
        answer = await chat_completion_sync("What is an LLM agent?")
        print("LLM agent definition:", answer)

    asyncio.run(main())
