from anthropic import Anthropic
import asyncio
from prompts import SYSTEM_PROMPT
from google import genai
from openai import OpenAI
from typing import Optional, Callable, Any


async def retry_with_backoff(
    call_agent_api: Callable[[], Any],
    request_context: Optional[str] = None,
    max_retries: int = 3,
    backoff_delays: list[int] = None,
) -> Any:
    """Execute a function with retry logic and exponential backoff.

    Args:
        call_agent_api: The function to call (synchronous)
        request_context: Context string for logging
        max_retries: Maximum number of retry attempts
        backoff_delays: List of delays (in seconds) to wait after each failure

    Returns:
        The response from call_agent_api

    Raises:
        RuntimeError: If all retry attempts fail
    """
    if backoff_delays is None:
        backoff_delays = [10, 30]  # Seconds to wait after 1st and 2nd failures

    last_error = None
    loop = asyncio.get_event_loop()

    for attempt in range(1, max_retries + 1):
        try:
            print(f"{request_context} (attempt {attempt}/{max_retries})")
            response = await loop.run_in_executor(None, call_agent_api)
            return response  # Success
        except Exception as e:
            last_error = e
            print(f"Error on attempt {attempt}/{max_retries}: {e}")
            if attempt < max_retries:
                delay = backoff_delays[attempt - 1]
                print(f"Retrying in {delay} seconds...")
                await asyncio.sleep(delay)
            else:
                # All retries exhausted - raise to get human intervention
                print(
                    f"All {max_retries} attempts failed. Requires human intervention."
                )
                raise RuntimeError(
                    f"Agent API failed after {max_retries} attempts: {last_error}"
                ) from last_error


async def agent(
    prompt: str,
    max_tokens=5000,
    thinking_budget=0.95,
    output_format=None,
    request_context=None,
    run_id: Optional[str] = None,
):
    """Route to the appropriate agent based on the run configuration.

    Args:
        prompt: The prompt to send to the agent
        max_tokens: Maximum tokens for the response
        thinking_budget: Budget for thinking tokens (0-1)
        output_format: Optional structured output format
        request_context: Context string for logging
        run_id: The run ID to determine which agent to use. If None, uses current run.

    Returns:
        Tuple of (response, thinking_text)
    """
    # Import here to avoid circular dependency
    from db import get_run_agent, get_current_run_id_from_db

    # Get run_id if not provided
    if run_id is None:
        run_id = get_current_run_id_from_db()

    # Get the agent for this run
    agent_name = None
    if run_id:
        agent_name = get_run_agent(run_id)

    # Default to gemini if no agent is specified
    if agent_name is None:
        agent_name = "gemini"

    # Route to the appropriate agent
    if agent_name.lower() == "claude":
        return await claude(
            prompt, max_tokens, thinking_budget, output_format, request_context
        )
    elif agent_name.lower() == "gemini":
        return await gemini(
            prompt, max_tokens, thinking_budget, output_format, request_context
        )
    elif agent_name.lower() == "openai":
        return await openai_agent(
            prompt, max_tokens, thinking_budget, output_format, request_context
        )
    else:
        raise ValueError(
            f"Unknown agent: {agent_name}. Must be 'claude', 'gemini', or 'openai'."
        )


async def claude(
    prompt: str,
    max_tokens=5000,
    thinking_budget=0.95,
    output_format=None,
    request_context=None,
):
    client = Anthropic()
    args = {
        "model": "claude-sonnet-4-5-20250929",
        "max_tokens": max_tokens,
        "system": [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {
                    "type": "ephemeral",
                },
            }
        ],
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }
    if output_format:
        args["output_format"] = output_format
        args["betas"] = ["structured-outputs-2025-11-13"]
    if thinking_budget:
        assert thinking_budget > 0.0 and thinking_budget < 1, (
            "Percent thinking must be between 0.9 and 1"
        )
        args["thinking"] = {
            "type": "enabled",
            "budget_tokens": int(max_tokens * thinking_budget),
        }

    def call_agent_api():
        if output_format:
            print("Called claude.")
            response = client.beta.messages.parse(**args)
            return response.parsed_output, response.content[0].thinking
        else:
            response = client.messages.create(**args)
            return response.content[1].text, response.content[0].thinking

    return await retry_with_backoff(call_agent_api, request_context)


async def gemini(
    prompt: str,
    max_tokens=5000,
    thinking_budget=0.95,
    output_format=None,
    request_context=None,
):
    """Call Google's Gemini API with similar interface to claude function.

    Note: thinking_budget parameter is accepted for API compatibility but not used,
    as Gemini doesn't have an equivalent thinking budget feature.
    """
    client = genai.Client()
    args = {
        "model": "gemini-3-flash-preview",
        "config": {
            "max_output_tokens": max_tokens,
            "system_instruction": SYSTEM_PROMPT,
            "thinking_config": {
                "thinking_level": "high",
                "include_thoughts": True,
            },
        },
        "contents": prompt,
    }

    if output_format:
        args["config"]["response_mime_type"] = "application/json"
        args["config"]["response_schema"] = output_format.model_json_schema()

    def call_agent_api():
        response = client.models.generate_content(**args)
        thought = "\n".join(
            x.text
            for x in filter(
                lambda x: x.text and x.thought, response.candidates[0].content.parts
            )
        )
        if output_format:
            return output_format.model_validate_json(response.text), thought
        return response, thought

    return await retry_with_backoff(call_agent_api, request_context)


async def openai_agent(
    prompt: str,
    max_tokens=10000,
    thinking_budget=0.95,
    output_format=None,
    request_context=None,
):
    """Call OpenAI's API with similar interface to claude and gemini functions.

    Note: thinking_budget parameter is accepted for API compatibility but not used,
    as OpenAI doesn't have an equivalent thinking budget feature.
    """
    client = OpenAI()
    args = {
        "model": "gpt-5.2-2025-12-11",
        "reasoning": {"effort": "high", "summary": "auto"},
        # "max_output_tokens": max_tokens,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": prompt,
            },
        ],
    }

    if output_format:
        args["text_format"] = output_format

    def call_agent_api():
        response = client.responses.parse(**args)
        print(response)
        reasoning = ""

        for section in response.output[0].summary:
            reasoning += section.text + "\n"

        if output_format:
            if response.output_parsed is None:
                raise ValueError("Output parsed is None")
            return response.output_parsed, reasoning
        return response.output_text, reasoning

    return await retry_with_backoff(call_agent_api, request_context)
