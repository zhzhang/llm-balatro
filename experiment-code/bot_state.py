"""Functions for converting game state to string representations."""

from enum import StrEnum
from typing import List, Optional, Set

from pydantic import BaseModel, field_validator, model_validator

from db import get_game_object_note
from game_definitions import VOUCHERS_BY_KEY, BOSS_BLINDS
from prompts import COMMAND_DESCRIPTIONS
from typing import Dict, Tuple


def hand_to_string(hand):
    acc = "Hand:\n"
    for i, card in enumerate(hand):
        acc += f"{i + 1}: {card_like_repr(card)}\n"
    return acc


def deck_remaining_to_string(deck):
    if len(deck) == 0:
        return "Cards Remaining in Deck: None\n"
    # acc = f"Cards Remaining in Deck ({len(deck)} cards):\n"
    # for i, card in enumerate(deck):
    #     acc += f"{card_like_repr(card, show_facedown=True)}\n"
    # return acc
    acc = f"Cards Remaining in Deck ({len(deck)} cards):\n"
    count_by_suit = {}
    count_by_rank = {}
    for card in deck:
        if " of " not in card["name"]:
            continue
        rank, suit = card["name"].split(" of ")
        count_by_suit[suit] = count_by_suit.get(suit, 0) + 1
        count_by_rank[rank] = count_by_rank.get(rank, 0) + 1
    acc += "Cards remaining in deck by suit:\n"
    for suit, count in count_by_suit.items():
        acc += f"{suit}: {count} cards\n"
    acc += "Cards remaining in deck by rank:\n"
    for rank, count in count_by_rank.items():
        acc += f"{rank}: {count} cards\n"
    return acc


def jokers_block(jokers):
    if len(jokers) == 0:
        return "Owned Jokers: None\n"
    acc = "Owned Jokers:\n"
    for i, joker in enumerate(jokers):
        acc += f"{i + 1}: {card_like_repr(joker)}. Sells for: ${joker['sells_for']}\n"
    return acc


def consumeables_block(consumeables):
    if len(consumeables) == 0:
        return "Owned Consumeables: None\n"
    acc = "Owned Consumeables:\n"
    for i, consumeable in enumerate(consumeables):
        acc += f"{i + 1}: {card_like_repr(consumeable)}. Sells for: ${consumeable['sells_for']}\n"
    return acc


def tags_block(tags):
    if len(tags) == 0:
        return "Owned Tags: None\n"
    acc = "Owned Tags:\n"
    for i, tag in enumerate(tags):
        acc += f"{i + 1}: {tag['name']} - {tag['description']}\n"
    return acc


def get_card_description(obj, show_compatibility=True):
    if obj["name"] == "Blueprint":
        return "Copies ability of Joker to the right, if compatible." + (
            f" Current compatibility: {obj['copy_compatible']}"
            if show_compatibility
            else ""
        )
    elif obj["name"] == "Brainstorm":
        return "Copies the ability of leftmost Joker, if compatible." + (
            f" Current compatibility: {obj['copy_compatible']}"
            if show_compatibility
            else ""
        )
    else:
        return obj["main_description"]


def card_like_repr(obj, show_facedown=False, show_compatibility=True):
    if obj["facing"] == "back" and not show_facedown:
        return "Name: Unknown. Description: Flipped face down."
    segments = [
        f"Name: {obj['name']}. Description: {get_card_description(obj, show_compatibility)}"
    ]
    if "secondary_description" in obj and obj["secondary_description"]:
        segments.append(f"Secondary Description: {obj['secondary_description']}")
    if "rarity" in obj:
        rarity = obj["rarity"]
        if rarity == 1:
            rarity = "Common"
        elif rarity == 2:
            rarity = "Uncommon"
        elif rarity == 3:
            rarity = "Rare"
        elif rarity == 4:
            rarity = "Legendary"
        segments.append(f"Rarity: {rarity}")
    if "edition" in obj:
        segments.append(f"Edition: {obj['edition']}")
    if (
        "enhancement" in obj
        and obj["enhancement"] != obj["name"]
        and obj["enhancement"] != "Default Base"
    ):
        segments.append(f"Enhancement: {obj['enhancement']}")
    if "seal" in obj:
        segments.append(f"Seal: {obj['seal']}")
    return ". ".join(segments)


def pack_choices_block(pack_choices):
    acc = "Booster Pack Choices:\n"
    for i, card in enumerate(pack_choices):
        acc += f"{i + 1}: {card_like_repr(card)}\n"
    return acc


def current_blind_info(state):
    for blind in ["Small", "Big", "Boss"]:
        blind_info = state["blind_info"][blind]
        if blind_info["state"] == "Current":
            acc = f"Current Blind: {blind}.\n"
            if "boss_description" in blind_info:
                acc += f"Boss Description: {blind_info['boss_description']}.\n"
            acc += f"Chips Needed: {blind_info['chips_needed']}\n"
            return acc


def shop_block(state, shop_type, shop_card_key):
    cards = state[shop_card_key]
    if len(cards) == 0:
        return f"{shop_type}: None\n"
    acc = f"{shop_type}:\n"
    for i, card in enumerate(cards):
        acc += f"{i + 1}: {card_like_repr(card, show_compatibility=False)}. Cost: ${card['cost']}\n"
    return acc


def build_hand_levels_string(hand_levels):
    acc = "## Hand Levels:\n"
    for hand_name, hand_level in hand_levels.items():
        acc += f"{hand_name}: Level {hand_level['level']}, Base Chips {hand_level['chips']}, Base Mult {hand_level['mult']}, Times Played {hand_level['times_played']}\n"
    return acc


def build_last_hands_string(played_hands):
    if not played_hands or len(played_hands) == 0:
        return "## Last Played Hands: None\n"
    # Get the last 7 hands (most recent first)
    last_hands = played_hands[-7:][::-1]
    acc = "## Last Played Hands (most recent first):\n"
    for hand in last_hands:
        acc += f"{hand['hand_name']} - {hand['chips_earned']:,} chips (Ante: {hand['ante']}, Blind: {hand['blind']})\n"
    return acc


def vouchers_block(owned_vouchers):
    if len(owned_vouchers) == 0:
        return "Owned Vouchers: None\n"
    acc = "Owned Vouchers:\n"
    for i, voucher_key in enumerate(owned_vouchers):
        voucher = VOUCHERS_BY_KEY.get(voucher_key)
        if voucher:
            acc += f"{i + 1}: {voucher['name']} - {voucher['effect']}\n"
        else:
            acc += f"{i + 1}: {voucher_key} (unknown voucher)\n"
    return acc


def build_inventory_string(state):
    acc = ""
    acc += "## Inventory\n"
    acc += jokers_block(state["jokers"])
    acc += f"Max Jokers: {state['max_jokers']}\n"
    acc += consumeables_block(state["consumeables"])
    acc += f"Max Consumeables: {state['max_consumeables']}\n"
    acc += tags_block(state["tags"])
    acc += vouchers_block(state["owned_vouchers"])
    acc += f"Current Money: ${state['dollars']}\n"
    return acc


def build_commands_reference(possible_actions):
    """Build the commands reference from a list of possible actions."""
    acc = "# Available Commands\n"
    acc += "The possible commands in Balatro are all composed of a single word specifying the action, followed by any necessary positional arguments, which are lists of integers.\n"
    acc += "Note: all position arguments are 1-indexed.\n\n"
    acc += "The following commands are available in your current game state.\n"
    for action in possible_actions:
        if action in COMMAND_DESCRIPTIONS:
            acc += COMMAND_DESCRIPTIONS[action] + "\n"
    return acc


def _get_item_type_from_card(card) -> Optional[str]:
    """Determine the item type for database lookup from a card object."""
    card_type = card.get("type", "")
    if card_type == "joker":
        return "joker"
    elif card_type in ("Tarot", "Planet", "Spectral"):
        return "consumable"
    # Shop cards may have different type indicators
    if card.get("rarity") is not None and card_type != "hand":
        # Cards with rarity that aren't playing cards are likely jokers
        return "joker"
    return None


def collect_game_objects_from_states(
    states: List[dict],
) -> Dict[Tuple[str, str], str]:
    """Collect all game objects from a list of state objects.

    Scans the provided states for game objects including:
    - Owned jokers, consumables, vouchers, and tags
    - Items in the shop (cards and vouchers)
    - Items in booster pack choices
    - Boss blinds

    Args:
        states: List of game state dictionaries.

    Returns:
        Dictionary mapping (name, type) tuples to description strings.
        Each game object is included only once (deduplication by name+type).
    """
    game_objects: Dict[Tuple[str, str], str] = {}

    for state in states:
        game_step = state.get("state", "")

        # Owned jokers
        for joker in state.get("jokers", []):
            name = joker.get("name", "")
            if name:
                key = (name, "joker")
                if key not in game_objects:
                    description = joker.get("main_description", "")
                    if joker.get("secondary_description"):
                        description += f"\n{joker['secondary_description']}"
                    game_objects[key] = description

        # Owned consumables
        for consumable in state.get("consumeables", []):
            name = consumable.get("name", "")
            if name:
                key = (name, "consumable")
                if key not in game_objects:
                    description = consumable.get("main_description", "")
                    game_objects[key] = description

        # Owned vouchers
        for voucher_key in state.get("owned_vouchers", []):
            voucher = VOUCHERS_BY_KEY.get(voucher_key)
            if voucher:
                name = voucher["name"]
                key = (name, "voucher")
                if key not in game_objects:
                    description = voucher.get("effect", "")
                    game_objects[key] = description

        # Owned tags
        for tag in state.get("tags", []):
            name = tag.get("name", "")
            if name:
                key = (name, "tag")
                if key not in game_objects:
                    description = tag.get("description", "")
                    game_objects[key] = description

        # Shop items (when in shop)
        if game_step == "SHOP":
            # Shop cards
            for card in state.get("shop_cards", []):
                item_type = _get_item_type_from_card(card)
                if item_type:
                    name = card.get("name", "")
                    if name:
                        key = (name, item_type)
                        if key not in game_objects:
                            description = card.get("main_description", "")
                            if card.get("secondary_description"):
                                description += f"\n{card['secondary_description']}"
                            game_objects[key] = description

            # Shop vouchers
            for voucher in state.get("shop_vouchers", []):
                name = voucher.get("name", "")
                if name:
                    key = (name, "voucher")
                    if key not in game_objects:
                        description = voucher.get("main_description", "")
                        game_objects[key] = description

        # Pack choices (when opening a booster pack)
        if "PACK" in game_step:
            for card in state.get("pack_choices", []):
                name = card.get("name", "")
                if not name:
                    continue

                if game_step == "BUFFOON_PACK":
                    key = (name, "joker")
                    if key not in game_objects:
                        description = card.get("main_description", "")
                        if card.get("secondary_description"):
                            description += f"\n{card['secondary_description']}"
                        game_objects[key] = description
                elif game_step in ("TAROT_PACK", "SPECTRAL_PACK", "PLANET_PACK"):
                    key = (name, "consumable")
                    if key not in game_objects:
                        description = card.get("main_description", "")
                        game_objects[key] = description

        # Blind select - check tags and boss blinds
        if game_step == "BLIND_SELECT":
            for blind in ["Small", "Big", "Boss"]:
                blind_info = state.get("blind_info", {}).get(blind, {})

                # Check skip tags
                tag_name = blind_info.get("tag")
                if tag_name:
                    key = (tag_name, "tag")
                    if key not in game_objects:
                        description = blind_info.get("tag_description", "")
                        game_objects[key] = description

                # Check boss blinds - analyze when we see them in blind select
                if blind == "Boss":
                    boss_desc = blind_info.get("boss_description")
                    if boss_desc:
                        # Load boss blinds data to match description to boss name
                        try:
                            # Try to match the description to a known boss
                            # Simple heuristic: check if key phrases from the effect appear in the description
                            for boss in BOSS_BLINDS:
                                boss_name = boss["name"]
                                boss_effect = boss["effect"]
                                # Check if the current boss matches (simple substring match)
                                # This is a heuristic - the description format may vary
                                if any(
                                    phrase.lower() in boss_desc.lower()
                                    for phrase in boss_effect.split()[:3]
                                ):
                                    key = (boss_name, "boss_blind")
                                    if key not in game_objects:
                                        game_objects[key] = boss_effect
                                    break
                        except Exception:
                            pass  # Silently fail if we can't match boss data

    return game_objects


def build_game_object_notes_section(state) -> str:
    """Build a section containing agent's notes for relevant game objects.

    Includes notes for:
    - Owned jokers, consumables, vouchers, and tags
    - Items in the shop (cards and vouchers)
    - Items in booster pack choices
    - Boss blinds
    """
    game_step = state["state"]
    notes_parts = []
    seen_items: Set[tuple] = set()  # (name, type) pairs to avoid duplicates

    def add_note(name: str, item_type: str, category: str):
        """Add a note if it exists and hasn't been added yet."""
        key = (name, item_type)
        if key in seen_items:
            return
        seen_items.add(key)
        note = get_game_object_note(name, item_type)
        if note:
            notes_parts.append(f"### {name} ({item_type})\n{note}")

    # Owned jokers
    for joker in state.get("jokers", []):
        add_note(joker.get("name", ""), "joker", "owned")

    # Owned consumables
    for consumable in state.get("consumeables", []):
        add_note(consumable.get("name", ""), "consumable", "owned")

    # Owned vouchers
    for voucher_key in state.get("owned_vouchers", []):
        voucher = VOUCHERS_BY_KEY.get(voucher_key)
        if voucher:
            add_note(voucher["name"], "voucher", "owned")

    # Owned tags
    for tag in state.get("tags", []):
        add_note(tag.get("name", ""), "tag", "owned")

    # Shop items (when in shop)
    if game_step == "SHOP":
        # Shop cards (could be jokers or consumables)
        for card in state.get("shop_cards", []):
            item_type = _get_item_type_from_card(card)
            if item_type:
                add_note(card.get("name", ""), item_type, "shop")

        # Shop vouchers
        for voucher in state.get("shop_vouchers", []):
            add_note(voucher.get("name", ""), "voucher", "shop")

    # Pack choices (when opening a booster pack)
    if "PACK" in game_step:
        for card in state.get("pack_choices", []):
            if game_step == "BUFFOON_PACK":
                add_note(card.get("name", ""), "joker", "pack")
            elif game_step in ("TAROT_PACK", "SPECTRAL_PACK", "PLANET_PACK"):
                add_note(card.get("name", ""), "consumable", "pack")
            # Standard pack has playing cards, no notes for those

    # Blind select - check tags and boss blinds
    if game_step == "BLIND_SELECT":
        for blind in ["Small", "Big", "Boss"]:
            blind_info = state.get("blind_info", {}).get(blind, {})
            if blind_info.get("tag"):
                add_note(blind_info["tag"], "tag", "skip_reward")

            # Add boss blind notes if available
            if blind == "Boss":
                boss_desc = blind_info.get("boss_description")
                if boss_desc:
                    # Try to match boss description to known boss names
                    try:
                        # Try to match the description to a known boss
                        for boss in BOSS_BLINDS:
                            boss_name = boss["name"]
                            boss_effect = boss["effect"]
                            # Check if key phrases from the effect appear in the description
                            if any(
                                phrase.lower() in boss_desc.lower()
                                for phrase in boss_effect.split()[:3]
                            ):
                                add_note(boss_name, "boss_blind", "boss")
                                break
                    except Exception:
                        pass  # Silently fail if we can't load boss data

    if not notes_parts:
        return ""

    acc = "# Game Object Notes\n"
    acc += "\n\n".join(notes_parts)
    acc += "\n"
    return acc


def build_state_string(state, state_only=False):
    game_step = state["state"]
    acc = f"Ante: {state['ante']}/8, Round: {state['round_number']}\n"
    acc += f"Game Step: {game_step}\n"
    # Failed action from last turn
    if state.get("failed_action"):
        acc += "## Failed Action from Last Your Last Response\n"
        failed_action_info = state["failed_action"]
        action = failed_action_info["action"]
        positions = failed_action_info.get("positions", [])
        positions_str = " ".join(str(p) for p in positions) if positions else ""
        acc += f"Failed Action: {action} {positions_str}\n"
        acc += f"Reason: {failed_action_info['reason']}\n"
    # Inventory
    acc += build_inventory_string(state)
    if game_step == "BLIND_SELECT":
        acc += "## Blind Select Info\n"
        for blind in ["Small", "Big", "Boss"]:
            blind_info = state["blind_info"][blind]
            if blind_info["state"] == "Select":
                acc += f"Current Blind: {blind}\n"
                acc += f"Chips Needed: {blind_info['chips_needed']}\n"
                if "tag" in blind_info:
                    acc += f"Tag for skipping: {blind_info['tag']}, {blind_info['tag_description']}\n"
                if blind != "Boss":
                    acc += "Decide whether to play the current blind, or skip in return for the tag.\n"
            elif blind_info["state"] == "Upcoming":
                acc += f"Upcoming Blind: {blind}\n"
                acc += f"Chips Needed: {blind_info['chips_needed']}\n"
                if "tag" in blind_info:
                    acc += f"Tag for skipping: {blind_info['tag']}, {blind_info['tag_description']}\n"
            else:
                continue
            if blind == "Boss":
                acc += f"Boss Description: {blind_info['boss_description']}\n"
            acc += f"Reward: ${blind_info['reward']}\n"
    if game_step in ["SELECTING_HAND"]:
        acc += "## Current Round Info\n"
        acc += current_blind_info(state)
        acc += hand_to_string(state["hand"])
        acc += f"Remaining hands that can be played: {state['hands_left']}\n"
        acc += f"Remaining hands that can be discarded: {state['discards_left']}\n"
        # acc += "The above numbers are the number of TIMES left that you can use the 'play' or 'discard' commands, respectively, not the number of cards you can play or discard. You may always play or discard up to 5 cards per use of the 'play' or 'discard' commands.\n"
        if state.get("forced_card_index") and not state.get("boss_blind_disabled"):
            index = state["forced_card_index"]
            acc += f"Cerulean Bell Forced Selected Card: {index} - {card_like_repr(state['hand'][index - 1])}\n"
            acc += "Any positions array included with your action must include the forced card index."
        if state.get("boss_blind_disabled"):
            acc += "Boss Blind effects have been disabled."
        acc += f"Current Chips: {state['chips']}\n"
        acc += deck_remaining_to_string(state["deck"])
    if game_step == "SHOP":
        acc += "## Shop Info\n"
        acc += shop_block(state, "Shop Cards", "shop_cards")
        acc += shop_block(state, "Shop Boosters", "shop_boosters")
        acc += shop_block(state, "Shop Vouchers", "shop_vouchers")
        acc += f"Current Reroll Cost: ${state['reroll_cost']}\n"
        acc += f"Can Reroll Boss: {'Yes' if state.get('can_reroll_boss') else 'No'}\n"
        if state.get("can_reroll_boss"):
            acc += "Boss Reroll Cost: $10\n"
    if "PACK" in game_step:
        acc += "## Pack Choices\n"
        acc += pack_choices_block(state["pack_choices"])
    if game_step == "SPECTRAL_PACK" or game_step == "TAROT_PACK":
        acc += hand_to_string(state["hand"])
    acc += "# Run Metadata\n"
    acc += build_hand_levels_string(state["hand_levels"])
    acc += build_last_hands_string(state.get("played_hands", []))
    acc += "\n"
    return acc


def build_action_prompt_suffix(state):
    # Add available commands based on current state
    possible_actions = get_possible_actions(state)
    acc = build_commands_reference(possible_actions)
    acc += "\n#Task\nAnalyze the total game state and context above, and respond with the appropriate action to take next."
    return acc


def get_possible_actions(state):
    """Get the list of possible actions for the current game state."""
    possible_actions = []
    st = state["state"]
    if st == "BLIND_SELECT":
        possible_actions.append("play_round")
        if not state.get("blind_info", {}).get("Boss", {}).get("state") == "Select":
            # Only show skip round if the boss blind is not the current blind
            possible_actions.append("skip_round")
        if state.get("can_reroll_boss"):
            possible_actions.append("reroll_boss")
    # All below states can do the following 4 actions
    possible_actions.append("use_consumable")
    possible_actions.append("sell_consumable")
    possible_actions.append("rearrange_jokers")
    possible_actions.append("sell_joker")
    if st == "SHOP":
        possible_actions.append("buy_card")
        possible_actions.append("buy_booster")
        possible_actions.append("buy_voucher")
        possible_actions.append("buy_and_use_consumable")
        possible_actions.append("round_select")
        possible_actions.append("reroll_shop")
    if "PACK" in st:
        possible_actions.append("select")
        possible_actions.append("skip_booster")
    if st == "SELECTING_HAND":
        possible_actions.append("play")
        possible_actions.append("discard")
    if st == "SPECTRAL_PACK" or st == "TAROT_PACK" or st == "SELECTING_HAND":
        possible_actions.append("rearrange_hand")
    return possible_actions


def action_schema(state):
    possible_actions = get_possible_actions(state)
    print(possible_actions)
    hand_types = [
        "high card",
        "pair",
        "two pair",
        "three of a kind",
        "straight",
        "flush",
        "full house",
        "four of a kind",
        "straight flush",
        "royal flush",
        "five of a kind",
        "flush house",
        "flush five",
    ]
    possible_actions_enum = StrEnum("PossibleActions", possible_actions)
    possible_hand_types_enum = StrEnum("PossibleHandTypes", hand_types)

    class Action(BaseModel):
        action: possible_actions_enum
        positions: Optional[List[int]] = None
        intended_hand_type: Optional[possible_hand_types_enum] = None
        estimated_chips: Optional[int] = None

        @field_validator("action", mode="before")
        @classmethod
        def strip_whitespace(cls, v):
            if isinstance(v, str):
                return "".join(v.split())
            return v

        @model_validator(mode="after")
        def validate_positions_required(self):
            """Validate that actions requiring positions have non-empty positions."""
            actions_without_positions = {
                "play_round",
                "skip_round",
                "reroll_shop",
                "round_select",
                "skip_booster",
            }
            if self.action not in actions_without_positions:
                if not self.positions or len(self.positions) == 0:
                    raise ValueError(
                        f"Action '{self.action}' requires at least one position argument"
                    )
            if self.action == "play":
                if not self.intended_hand_type:
                    raise ValueError("Action 'play' requires an intended hand type")
                if self.intended_hand_type not in hand_types:
                    raise ValueError(
                        f"Invalid intended hand type: {self.intended_hand_type}"
                    )
                if not self.estimated_chips:
                    raise ValueError("Action 'play' requires an estimated chips value")
            if self.action == "play" or self.action == "discard":
                if (
                    not self.positions
                    or len(self.positions) == 0
                    or len(self.positions) > 5
                ):
                    raise ValueError(
                        f"Action '{self.action}' requires between 1 and 5 position arguments"
                    )
            if (
                self.positions
                and len(self.positions) > 0
                and "forced_card_index" in state
                and not state.get("boss_blind_disabled")
            ):
                index = state["forced_card_index"]
                if index not in self.positions:
                    raise ValueError(
                        f"Boss Blind Cerulean Bell requires the forced card index ({index}) to be in the positions"
                    )
            return self

    return Action
