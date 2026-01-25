"""State-responding action generating logic for the Balatro bot."""

import asyncio
import server
import traceback
from datetime import datetime
from typing import Optional

from agent_api import agent
from pydantic import BaseModel, model_validator

from bot_state import (
    build_state_string,
    action_schema,
    collect_game_objects_from_states,
    build_action_prompt_suffix,
)
from db import (
    get_all_game_object_notes,
    get_all_game_runs_with_outcomes,
    get_game_object_note,
    get_game_plan,
    get_next_turn,
    get_run_history,
    get_turn_state,
    save_agent_reply,
    save_game_object_note,
    save_game_plan,
    save_state,
    update_hand_result,
    set_win_status,
)
from game_definitions import (
    JOKERS,
    VOUCHERS,
    BOSS_BLINDS,
    get_all_consumables,
)
from prompts import (
    build_game_plan_prompt,
    build_initial_boss_blind_analysis_prompt,
    build_initial_item_analysis_prompt,
)


async def generate_game_plan(run_id: str) -> Optional[str]:
    """Generate a game plan by synthesizing all past reflections and outcomes."""
    past_runs = get_all_game_runs_with_outcomes()

    if not past_runs:
        print("No past runs to generate game plan from.")
        return None

    # Build the past reflections summary
    reflections_text = ""
    game_num = 0
    for run in past_runs:
        # Skip records missing any required fields
        if (
            run.get("final_ante") is None
            or run.get("final_round") is None
            or run.get("best_hand") is None
            or not run.get("reflection")
        ):
            continue

        game_num += 1
        reflections_text += f"\n## Game {game_num} (Run ID: {run['run_id']})\n"
        reflections_text += f"Final Ante: {run['final_ante']}\n"
        reflections_text += f"Final Round: {run['final_round']}\n"
        reflections_text += f"Best Hand Chips: {run['best_hand']}\n"
        reflections_text += f"\nReflection:\n{run['reflection']}\n"

    # Load card reference data
    card_reference = server.load_card_reference_data()

    # Build the game plan prompt
    prompt = build_game_plan_prompt(reflections_text, card_reference)

    try:
        plan_text, _ = await agent(
            prompt,
            max_tokens=6000,
            thinking_budget=0.33,
            request_context=f"Game plan generation for run {run_id}",
            run_id=run_id,
        )

        save_game_plan(run_id, plan_text)
        print(f"Game plan generated for run {run_id}")
        print(plan_text)
        return plan_text

    except Exception as e:
        print(f"Error generating game plan: {e}")
        return None


def build_previous_turn_context(
    run_id: str, n_turns: Optional[int] = None, ante: Optional[int] = None
) -> str:
    """Build context from previous turns.

    Args:
        run_id: The run ID to get history for.
        n_turns: Number of previous turns to include. If None, includes only the last turn.
        ante: Optional ante filter (not yet implemented).

    Returns a single formatted string containing the previous game states
    and the agent's actions/reasoning, to provide context for the current state.
    """
    history = get_run_history(run_id)
    context_parts = []

    if not history:
        return ""

    # Group entries by turn
    turns = {}
    for entry in history:
        turn = entry["turn"]
        if turn not in turns:
            turns[turn] = {}
        turns[turn][entry["type"]] = entry["data"]

    if not turns:
        return ""

    # Get the turns to include
    sorted_turns = sorted(turns.keys())
    if n_turns is None:
        # Default: only the last turn
        turns_to_include = sorted_turns[-1:] if sorted_turns else []
    else:
        # Include the last n_turns
        turns_to_include = sorted_turns[-n_turns:] if n_turns > 0 else []

    # Build context for each turn in chronological order
    for turn_num in turns_to_include:
        turn_data = turns[turn_num]

        # Add game state
        if "game_state" in turn_data:
            game_state_data = turn_data["game_state"]
            state_string = game_state_data.get("state_string", "")
            context_parts.append(
                f"[PREVIOUS STATE - Turn {turn_num + 1}]\n{state_string}"
            )

        # Add agent's action and reasoning
        if "agent_reply" in turn_data:
            agent_data = turn_data["agent_reply"]
            action = agent_data.get("action", "")
            positions = agent_data.get("positions", [])
            reasoning = agent_data.get("reasoning", "")
            positions_str = " ".join(str(p) for p in positions) if positions else ""
            command = f"{action} {positions_str}".strip()

            if action == "play":
                intended_hand_type = agent_data.get("intended_hand_type", "")
                estimated_chips = agent_data.get("estimated_chips", "")
                command += f" {intended_hand_type} {estimated_chips}"

            content = f"[MY PREVIOUS ACTION - Turn {turn_num + 1}]\n"
            if reasoning:
                content += f"Reasoning: {reasoning}\n"
            content += f"Command: {command}\n"

            context_parts.append(content)

    return "\n\n".join(context_parts) + "\n"


async def _analyze_new_game_object(
    object_name: str, object_type: str, description: str
) -> dict:
    """Generate initial analysis for a new game object based on its description.

    This is called when a game object is first encountered (before play with it occurs).

    Args:
        client: Anthropic client instance.
        model: The model to use for analysis.
        object_name: Name of the game object.
        object_type: One of "joker", "consumable", "voucher", "tag", or "boss_blind".
        description: The object's description text.

    Returns:
        Dictionary with 'name', 'type', and 'notes' keys.
    """
    # Check if we already have notes for this object in the database
    existing_notes = get_game_object_note(object_name, object_type)
    if existing_notes:
        print(f"Loading existing notes for {object_name} ({object_type}) from database")
        return {
            "name": object_name,
            "type": object_type,
            "notes": existing_notes,
        }

    # Get all objects of the same type from game definitions
    if object_type == "joker":
        all_objects = JOKERS
    elif object_type == "consumable":
        all_objects = get_all_consumables()
    elif object_type == "voucher":
        all_objects = VOUCHERS
    elif object_type == "boss_blind":
        all_objects = BOSS_BLINDS
    else:
        # For tags or other types not in game definitions, skip similarity lookup
        all_objects = []

    # Filter to only objects that have notes in the database
    all_notes = get_all_game_object_notes()
    objects_with_notes = {
        note["name"] for note in all_notes if note["type"] == object_type
    }
    all_objects = [obj for obj in all_objects if obj["name"] in objects_with_notes]

    print(f"Found {len(all_objects)} total {object_type}(s) in game definitions")

    # Build context from similar objects if any exist
    similar_objects_context = ""
    if all_objects:
        # Create a list of object names for Claude to consider
        object_names_list = [obj["name"] for obj in all_objects]
        names_text = "\n".join(f"- {name}" for name in object_names_list)

        # Ask Claude to identify the 3 most similar objects
        similarity_prompt = f"""You are analyzing a new {object_type} called "{object_name}" with the following description:

{description}

Here are all the {object_type}s in the game:

{names_text}

Based on the description of {object_name}, which 3 {object_type}s from the above list are most similar in function, mechanics, or strategic role? 

Please respond with ONLY the names of the 3 most similar {object_type}s, one per line, with no additional text or explanation."""

        similarity_response, _ = await agent(
            similarity_prompt,
            max_tokens=2000,
            thinking_budget=0.9,
            request_context=f"Finding similar objects for {object_name}",
        )

        # Parse the response to get the 3 object names
        similar_names = []
        try:
            similar_names = [
                line.strip().strip("-").strip()
                for line in similarity_response.strip().split("\n")
                if line.strip()
            ][:3]
        except Exception as e:
            print(f"Error parsing similarity response: {e}")
            return []

        print(f"Agent identified similar {object_type}s: {similar_names}")

        # Look up the definition and analysis for these objects
        similar_analyses = []
        for similar_name in similar_names:
            # Find the matching object definition
            matching_obj = next(
                (obj for obj in all_objects if obj["name"] == similar_name),
                None,
            )
            if matching_obj:
                # Get the description from the game definition
                obj_description = matching_obj.get("effect") or matching_obj.get(
                    "description", ""
                )

                # Try to get existing analysis from database
                existing_notes = get_game_object_note(similar_name, object_type)

                similar_analyses.append(
                    {
                        "name": similar_name,
                        "description": obj_description,
                        "notes": existing_notes,
                    }
                )

        # Build the context section if we found any definitions
        if similar_analyses:
            print(
                f"Including information from {len(similar_analyses)} similar objects: {[a['name'] for a in similar_analyses]}"
            )
            similar_objects_context = "\n\n## Similar Objects for Reference\n\n"
            similar_objects_context += (
                "For context, here are similar objects and their definitions:\n\n"
            )
            for analysis in similar_analyses:
                similar_objects_context += f"### {analysis['name']}\n\n"
                similar_objects_context += (
                    f"**Description:** {analysis['description']}\n\n"
                )
                if analysis["notes"]:
                    similar_objects_context += (
                        f"**Our Analysis:**\n{analysis['notes']}\n\n"
                    )
                else:
                    similar_objects_context += "**Our Analysis:** Not yet analyzed.\n\n"
        else:
            print("No matching definitions found for the identified similar objects")

    # Build the main analysis prompt with the similar objects context
    if object_type == "boss_blind":
        prompt = build_initial_boss_blind_analysis_prompt(object_name, description)
    else:
        prompt = build_initial_item_analysis_prompt(
            object_name, object_type, description
        )

    # Append the similar objects context to the prompt
    prompt += similar_objects_context

    response, _ = await agent(
        prompt,
        max_tokens=5000,
        thinking_budget=0.66,
        request_context=f"Analysis for {object_name} ({object_type})",
    )
    return {
        "name": object_name,
        "type": object_type,
        "notes": f"## Initial Impression (before play)\n\n{response}",
    }


async def analyze_new_game_objects_in_state(state) -> None:
    """Identify and analyze any new game objects in the current game state.

    This function scans the state for game objects (items and boss blinds) that don't
    have notes yet, and generates initial impressions for them based on their descriptions.

    Args:
        state: The current game state dictionary.
        model: The model to use for analysis.
    """
    # Collect all game objects from the current state
    game_objects = collect_game_objects_from_states([state])

    # Filter to only items that don't have notes yet
    new_items_to_analyze = []  # List of (name, type, description) tuples
    for (name, item_type), description in game_objects.items():
        if not get_game_object_note(name, item_type):
            new_items_to_analyze.append((name, item_type, description))

    # If there are new game objects, analyze them in parallel
    if new_items_to_analyze:
        print(f"Analyzing {len(new_items_to_analyze)} new game objects...")
        tasks = []
        for name, item_type, description in new_items_to_analyze:
            tasks.append(_analyze_new_game_object(name, item_type, description))

        try:
            results = await asyncio.gather(*tasks)
            # Save each game object's notes to the database
            for result in results:
                save_game_object_note(result["name"], result["type"], result["notes"])
                print(
                    f"Saved initial impression for {result['type']}: {result['name']}"
                )
        except Exception as e:
            print(f"Error during new game object analysis: {e}")
            traceback.print_exc()


async def process_game_over_state(state):
    """Process game over state asynchronously."""
    # Terminate the game before reflection
    if server.game_process and server.game_process.returncode is None:
        try:
            server.game_process.terminate()
            print("Game terminated.")
        except Exception as e:
            print(f"Failed to terminate game: {e}")
    # Generate and store reflection on game over
    # await generate_game_summary(state)

    from server import start_game, get_current_run_id

    run_id = get_current_run_id()
    set_win_status(run_id, False)
    await start_game()


async def update_previous_turn_hand_result(run_id, turn, state):
    if turn > 0:
        prev_turn_data = get_turn_state(run_id, turn - 1)
        if not prev_turn_data:
            raise ValueError(f"Previous turn data not found for turn {turn - 1}")
        prev_game_state = prev_turn_data.get("game_state", {})
        prev_state_type = prev_game_state.get("state")

        if prev_state_type == "SELECTING_HAND":
            played_hands = state.get("played_hands", [])
            if played_hands:
                last_played_hand = played_hands[-1]
                hand_result = {
                    "hand_type": last_played_hand.get("hand_name"),
                    "chips_earned": last_played_hand.get("chips_earned"),
                }
                update_hand_result(run_id, turn - 1, hand_result)
                print(f"Updated turn {turn - 1} with hand result: {hand_result}")


class SurpriseAnalysis(BaseModel):
    """Analysis of whether the outcome of an action was surprising."""

    surprise_detected: bool
    explanation: Optional[str] = None

    @model_validator(mode="after")
    def validate_explanation(self):
        """Ensure explanation is provided when surprise is detected and absent when not."""
        if self.surprise_detected and not self.explanation:
            raise ValueError(
                "explanation must be provided when surprise_detected is true"
            )
        if not self.surprise_detected and self.explanation is not None:
            raise ValueError(
                "explanation must not be provided when surprise_detected is false"
            )
        return self


def get_strategy(run_id):
    strategy_string = ""
    saved_plan = get_game_plan(run_id)
    if saved_plan:
        strategy_string = saved_plan
    return strategy_string


async def process_state_async(state):
    """Process game state asynchronously - saves action to DB for polling.

    This function is called as a background task when state is received.
    The action is saved to the database with sent_to_game=False, and the
    game polls the /action endpoint to retrieve it.
    """
    # Get or create run_id
    run_id = server.get_current_run_id()
    turn = get_next_turn(run_id)

    await update_previous_turn_hand_result(run_id, turn, state)

    if state["state"] == "GAME_OVER":
        await process_game_over_state(state)
        return

    # Analyze any new game objects in the state (generate initial impressions)
    # This needs to complete BEFORE building state string so notes are available immediately
    # await analyze_new_game_objects_in_state(state)

    state_string = build_state_string(state)

    # Build the current turn's state prompt
    current_state_prompt = (
        f"[CURRENT STATE - Take action from this state]\n{state_string}"
    )

    # Start the prompt with the strategy
    prompt = """The following context includes three parts:
1) the state and your actions taken for the last few turns
2) the current game state that you must take action from
3) metadata about the current game state

"""

    prompt += get_strategy(run_id)

    # Build context from only the previous turn (before saving current)
    previous_turn_context = build_previous_turn_context(run_id, n_turns=3)

    # Build the user message content, including previous context if available
    if previous_turn_context:
        prompt += previous_turn_context
    prompt += current_state_prompt

    schema = action_schema(state)
    prompt += build_action_prompt_suffix(state)

    # Save game state and snapshot to database
    # This also broadcasts the game state to WebSocket clients
    game_state_data = {
        "game_state": state,
        "state_string": state_string,
        "prompt": prompt,
    }
    ante = state.get("ante")
    await save_state(run_id, turn, game_state_data, ante=ante)

    action, thinking_block = await agent(
        prompt,
        output_format=schema,
        request_context=f"Action for turn {turn}",
        run_id=run_id,
    )

    print("Action generated for turn ", turn)
    print(action.action, action.positions)

    # Save agent reply to database with sent_to_game=False
    # The game will poll /action endpoint to retrieve this
    agent_reply_data = {
        "action": action.action,
        "positions": action.positions,
        "reasoning": thinking_block,
    }
    if action.action == "play":
        agent_reply_data["intended_hand_type"] = action.intended_hand_type
        agent_reply_data["estimated_chips"] = action.estimated_chips
    save_agent_reply(run_id, turn, agent_reply_data, sent_to_game=False)

    # Broadcast agent response to WebSocket clients
    response_entry = {
        "type": "agent_response",
        "run_id": run_id,
        "turn": turn,
        "timestamp": datetime.now().isoformat(),
        "action": action.action,
        "positions": action.positions,
        "reasoning": thinking_block,
    }
    await server.broadcast_to_clients(response_entry)
