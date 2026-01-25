"""Post game analysis functions for the Balatro bot."""

import asyncio
import server
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

from agent_api import agent
from db import (
    get_game_object_note,
    get_run_history,
    get_run_history_by_ante,
    save_game_object_note,
    save_reflection,
    get_game_plan,
)
from bot_state import collect_game_objects_from_states
from prompts import (
    build_ante_summary_prompt,
    build_final_reflection_prompt,
    build_postgame_boss_blind_analysis_prompt,
    build_postgame_item_analysis_prompt,
)


def build_ante_history(ante_entries: list) -> str:
    """Build history string for a single ante from its entries."""
    # Group entries by turn
    turns = {}
    for entry in ante_entries:
        turn = entry["turn"]
        if turn < 0:
            continue
        if turn not in turns:
            turns[turn] = {}
        turns[turn][entry["type"]] = entry["data"]

    history_parts = []
    for turn_num in sorted(turns.keys()):
        turn_data = turns[turn_num]
        turn_str = f"--- Turn {turn_num + 1} ---\n"

        if "game_state" in turn_data:
            game_state_data = turn_data["game_state"]
            state_string = game_state_data.get("state_string", "")
            turn_str += f"Game State:\n{state_string}\n"

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

            turn_str += f"My Reasoning: {reasoning}\n"
            turn_str += f"My Action: {command}\n"

        history_parts.append(turn_str)

    return "\n".join(history_parts)


async def generate_ante_summary(
    ante_num: int, ante_history: str, later_summaries: str = ""
) -> str:
    """Generate a summary for a single ante, informed by summaries of later antes."""
    prompt = build_ante_summary_prompt(ante_num, ante_history, later_summaries)
    response, _ = await agent(
        prompt,
        max_tokens=8000,
        thinking_budget=0.5,
        request_context=f"Summary for ante {ante_num}",
    )
    return response


def build_chips_outcome_prompt(run_id: str) -> List[Dict[str, Any]]:
    """Build a list of hands played in a run with context about each hand.

    For each hand played, includes:
    - jokers: List of joker names available when the hand was played
    - consumables_used: Tarot and planet cards used since the previous hand
    - intended_hand_type: The agent's intended hand type
    - estimated_chips: The agent's estimated chips for the play
    - actual_hand_type: The actual hand type that was played
    - actual_chips: The actual chips earned
    - turn: The turn number
    - ante: The ante number

    Args:
        run_id: The run ID to analyze.

    Returns:
        List of dictionaries, one per hand played.

    Raises:
        ValueError: If any "selecting_hand" state with a "play" action doesn't have
                    hand_result data attached.
    """
    history = get_run_history(run_id)

    if not history:
        return []

    # Group entries by turn
    turns: Dict[int, Dict[str, Any]] = {}
    for entry in history:
        turn = entry["turn"]
        if turn not in turns:
            turns[turn] = {}
        turns[turn][entry["type"]] = entry

    hands_played = []
    consumables_used_since_last_hand: List[str] = []
    vouchers_redeemed_since_last_hand: List[str] = []

    for turn_num in sorted(turns.keys()):
        turn_data = turns[turn_num]

        game_state_entry = turn_data.get("game_state")
        agent_reply_entry = turn_data.get("agent_reply")

        if not game_state_entry:
            continue

        game_state_data = game_state_entry["data"]
        game_state = game_state_data.get("game_state", {})
        state_type = game_state.get("state")

        # Track consumable usage from agent replies
        if agent_reply_entry:
            agent_data = agent_reply_entry["data"]
            action = agent_data.get("action", "")

            # Track use_consumable actions for tarot/planet cards
            if action == "use_consumable":
                positions = agent_data.get("positions", [])
                consumables = game_state.get("consumeables", [])
                if positions and consumables:
                    # Get the consumable that was used (1-indexed position)
                    pos = positions[0] - 1  # Convert to 0-indexed
                    if 0 <= pos < len(consumables):
                        consumable = consumables[pos]
                        consumable_type = consumable.get("type", "")
                        # Only track tarot and planet cards
                        if consumable_type in ("Tarot", "Planet"):
                            consumables_used_since_last_hand.append(
                                consumable.get("name", "Unknown")
                            )

            # Track voucher purchases
            if action == "buy_voucher":
                positions = agent_data.get("positions", [])
                shop_vouchers = game_state.get("shop_vouchers", [])
                if positions and shop_vouchers:
                    pos = positions[0] - 1  # Convert to 0-indexed
                    if 0 <= pos < len(shop_vouchers):
                        voucher = shop_vouchers[pos]
                        vouchers_redeemed_since_last_hand.append(
                            voucher.get("name", "Unknown")
                        )

        # Process "selecting_hand" states where agent played a hand
        if state_type == "SELECTING_HAND" and agent_reply_entry:
            agent_data = agent_reply_entry["data"]
            action = agent_data.get("action", "")

            if action == "play":
                # Get hand result - skip if missing (can happen if game ended mid-hand)
                hand_result = game_state_entry.get("hand_result")
                if not hand_result:
                    print(
                        f"Warning: Turn {turn_num} has 'play' action but no hand_result, skipping"
                    )
                    continue

                # Build the hand entry
                jokers = game_state.get("jokers", [])
                joker_names = [j.get("name", "Unknown") for j in jokers]

                hand_entry = {
                    "turn": turn_num,
                    "ante": game_state.get("ante"),
                    "jokers": joker_names,
                    "consumables_used": list(consumables_used_since_last_hand),
                    "vouchers_redeemed": list(vouchers_redeemed_since_last_hand),
                    "intended_hand_type": agent_data.get("intended_hand_type"),
                    "estimated_chips": agent_data.get("estimated_chips"),
                    "actual_hand_type": hand_result.get("hand_type"),
                    "actual_chips": hand_result.get("chips_earned"),
                }

                hands_played.append(hand_entry)

                # Reset trackers after each hand played
                consumables_used_since_last_hand = []
                vouchers_redeemed_since_last_hand = []

    return hands_played


def _format_hands_data(hands_data: List[Dict[str, Any]]) -> str:
    """Format the full hands trajectory as a string for the prompt."""
    lines = []
    for hand in hands_data:
        ante = hand.get("ante", "?")
        turn = hand.get("turn", "?")
        jokers = hand.get("jokers", [])
        consumables_used = hand.get("consumables_used", [])
        vouchers_redeemed = hand.get("vouchers_redeemed", [])
        intended = hand.get("intended_hand_type", "?")
        estimated = hand.get("estimated_chips", "?")
        actual_type = hand.get("actual_hand_type", "?")
        actual_chips = hand.get("actual_chips", 0)

        jokers_str = ", ".join(jokers) if jokers else "None"
        consumables_str = ", ".join(consumables_used) if consumables_used else "None"
        vouchers_str = ", ".join(vouchers_redeemed) if vouchers_redeemed else "None"

        lines.append(
            f"Ante {ante}, Turn {turn}:\n"
            f"  Jokers: [{jokers_str}]\n"
            f"  Consumables used before hand: [{consumables_str}]\n"
            f"  Vouchers redeemed before hand: [{vouchers_str}]\n"
            f"  Intended: {intended} (est. {estimated:,} chips)\n"
            f"  Actual: {actual_type} for {actual_chips:,} chips"
        )
    return "\n\n".join(lines)


async def _analyze_game_object(
    object_name: str,
    object_type: str,
    hands_data: List[Dict[str, Any]],
) -> Dict[str, str]:
    """Generate analysis for a game object by examining the full hands trajectory.

    Args:
        client: Anthropic client instance.
        model: The model to use for analysis.
        object_name: Name of the game object to analyze.
        object_type: One of "joker", "consumable", "voucher", or "boss_blind".
        hands_data: Complete list of all hands played in the run.

    Returns:
        Dictionary with 'name', 'type', and 'notes' keys.
    """
    hands_text = _format_hands_data(hands_data)

    # Fetch previous notes for this game object from the database
    previous_notes = get_game_object_note(object_name, object_type)

    # Check if there's an initial impression to preserve
    previous_section = ""
    if previous_notes:
        previous_section = f"""
---
## Last analysis of this object

{previous_notes}

---
"""

    print(previous_section)

    # Different prompts for boss blinds vs items
    if object_type == "boss_blind":
        prompt = build_postgame_boss_blind_analysis_prompt(
            object_name, hands_text, previous_section
        )
    else:
        prompt = build_postgame_item_analysis_prompt(
            object_name, object_type, hands_text, previous_section
        )

    final_notes, _ = await agent(
        prompt,
        max_tokens=8000,
        thinking_budget=0.5,
        request_context=f"Analysis for {object_name} ({object_type})",
    )

    return {
        "name": object_name,
        "type": object_type,
        "notes": final_notes,
    }


async def generate_game_object_analysis(run_id: str) -> Optional[str]:
    """Generate an analysis of game objects (items and boss blinds) from the run.

    This function analyzes the run data to describe:
    - How items (jokers, consumables) affected chips earned
    - Synergies between items
    - How boss blinds were beaten and what strategies worked
    - When items should be prioritized and when they should not be

    Each game object is analyzed individually in parallel for faster processing.

    Args:
        run_id: The run ID to analyze.
        model: The model to use for analysis.

    Returns:
        The analysis text, or None if there's insufficient data.
    """
    print(f"Starting game object analysis for run {run_id}...")
    try:
        hands_data = build_chips_outcome_prompt(run_id)
    except ValueError as e:
        print(f"Could not build chips outcome data: {e}")
        return None

    if not hands_data:
        print("No hands data available for game object analysis")
        return None

    # Collect all game objects that appeared in the run by extracting states
    history = get_run_history(run_id)
    states = []
    for entry in history:
        if entry["type"] == "game_state":
            game_state_data = entry["data"]
            game_state = game_state_data.get("game_state", {})
            if game_state:
                states.append(game_state)

    game_objects = collect_game_objects_from_states(states)

    # Filter to only jokers and consumables that actually appeared in hands data
    jokers_in_hands = set()
    consumables_in_hands = set()

    for hand in hands_data:
        for joker_name in hand.get("jokers", []):
            jokers_in_hands.add(joker_name)
        for consumable_name in hand.get("consumables_used", []):
            consumables_in_hands.add(consumable_name)

    # Only analyze game objects that were actually used/present during hands
    objects_to_analyze = {}
    for (name, obj_type), description in game_objects.items():
        if obj_type == "joker" and name in jokers_in_hands:
            objects_to_analyze[(name, obj_type)] = description
        elif obj_type == "consumable" and name in consumables_in_hands:
            objects_to_analyze[(name, obj_type)] = description
        # TODO: Add boss_blind when we can properly track boss encounters

    if not objects_to_analyze:
        print("No game object data available for analysis")
        return None

    # Build list of analysis tasks for parallel execution
    tasks = []

    # Add analysis tasks for all game objects
    for (name, obj_type), description in objects_to_analyze.items():
        tasks.append(
            _analyze_game_object(
                name,
                obj_type,
                hands_data,
            )
        )

    print(f"Generating game object analysis for {len(tasks)} objects in parallel...")

    # Execute all analyses in parallel
    try:
        results = await asyncio.gather(*tasks)
    except Exception as e:
        print(f"Error during game object analysis: {e}")
        traceback.print_exc()
        return None

    # Save each game object's notes to the database and build combined analysis
    analysis_parts = []
    for result in results:
        try:
            save_game_object_note(result["name"], result["type"], result["notes"])
            print(f"Saved notes for {result['type']}: {result['name']}")
            analysis_parts.append(
                f"## {result['name']} ({result['type']})\n\n{result['notes']}"
            )
        except Exception as e:
            print(f"Error saving note for {result.get('name', 'unknown')}: {e}")

    return "\n\n".join(analysis_parts)


async def generate_reflection(state: dict, run_id: str) -> str:
    history_by_ante = get_run_history_by_ante(run_id)

    if not history_by_ante:
        print("No history found for this run")
        return "No history recorded for this run."

    # Determine outcome
    game_outcome = "unknown"
    if "game_result" in state:
        game_outcome = state["game_result"]
    elif state.get("state") == "GAME_OVER":
        game_outcome = "game ended"

    # Extract game over stats
    best_hand = state.get("best_hand")
    final_ante = state.get("final_ante")
    final_round = state.get("final_round")

    # Build game stats section
    game_stats = ""
    if best_hand is not None:
        game_stats += f"Best Hand Chips: {best_hand}\n"
    if final_ante is not None:
        game_stats += f"Final Ante: {final_ante}\n"
    if final_round is not None:
        game_stats += f"Final Round: {final_round}\n"

    print(f"Generating per-ante summaries for {len(history_by_ante)} antes...")
    print(game_stats)

    # Get valid antes (excluding 0 which means no ante info)
    valid_antes = [a for a in history_by_ante.keys() if a != 0]

    if not valid_antes:
        print("No valid antes found in history")
        return "No ante history recorded for this run."

    # Generate summaries in reverse order (highest ante first)
    # Each summary is informed by the summaries of later antes
    ante_summaries = {}
    accumulated_summaries = ""  # Summaries of later antes to provide context

    for ante_num in sorted(valid_antes, reverse=True):
        ante_entries = history_by_ante[ante_num]
        ante_history = build_ante_history(ante_entries)

        print(f"Generating summary for Ante {ante_num}...")
        summary = await generate_ante_summary(
            ante_num, ante_history, later_summaries=accumulated_summaries
        )
        ante_summaries[ante_num] = summary
        print(f"Ante {ante_num} summary generated.")

        # Add this summary to the accumulated context for earlier antes
        accumulated_summaries = (
            f"## Ante {ante_num} Summary\n{summary}\n\n" + accumulated_summaries
        )

    # Build the combined ante summaries text (in forward order for readability)
    summaries_text = ""
    for ante_num in sorted(ante_summaries.keys()):
        summaries_text += f"\n## Ante {ante_num} Summary\n{ante_summaries[ante_num]}\n"

    game_plan = get_game_plan(run_id)
    # Generate final reflection based on ante summaries
    final_reflection_prompt = build_final_reflection_prompt(
        game_plan, summaries_text, game_outcome, game_stats
    )

    print("Generating final reflection and game object analysis in parallel...")
    reflection_text, _ = await agent(
        final_reflection_prompt,
        max_tokens=8000,
        thinking_budget=0.5,
        request_context="Final reflection",
        run_id=run_id,
    )
    # Combine ante summaries, final reflection, and game object analysis for storage
    full_reflection = f"# Per-Ante Summaries\n{summaries_text}\n\n# Final Reflection\n{reflection_text}"
    return full_reflection


async def generate_game_summary(state):
    """Generate a reflection on the completed game and store it in the database.

    This function:
    1. Gets history grouped by ante
    2. Generates a summary for each ante
    3. Creates a final reflection based on the per-ante summaries
    4. Generates an item impact analysis for jokers and consumables
    """
    run_id = server.get_current_run_id()

    reflection, _ = await asyncio.gather(
        generate_reflection(state, run_id), generate_game_object_analysis(run_id)
    )

    # Extract game over stats
    best_hand = state.get("best_hand")
    final_ante = state.get("final_ante")
    final_round = state.get("final_round")

    # Save the reflection to the database
    save_reflection(
        run_id,
        reflection,
        best_hand=best_hand,
        final_ante=final_ante,
        final_round=final_round,
    )

    print(f"Game reflection saved for run {run_id}")
    # Broadcast reflection to WebSocket clients
    reflection_entry = {
        "type": "reflection",
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "reflection": reflection,
        "best_hand": best_hand,
        "final_ante": final_ante,
        "final_round": final_round,
    }
    await server.broadcast_to_clients(reflection_entry)
