"""Pydantic types for game state JSON received from the Balatro game."""

from enum import StrEnum
from typing import Annotated, Literal, Optional
from pydantic import BaseModel, Field


class GameState(StrEnum):
    """Possible game states/phases."""

    SELECTING_HAND = "SELECTING_HAND"
    SHOP = "SHOP"
    PLAY_TAROT = "PLAY_TAROT"
    HAND_PLAYED = "HAND_PLAYED"
    DRAW_TO_HAND = "DRAW_TO_HAND"
    NEW_ROUND = "NEW_ROUND"
    BLIND_SELECT = "BLIND_SELECT"
    ROUND_EVAL = "ROUND_EVAL"
    TAROT_PACK = "TAROT_PACK"
    SPECTRAL_PACK = "SPECTRAL_PACK"
    STANDARD_PACK = "STANDARD_PACK"
    BUFFOON_PACK = "BUFFOON_PACK"
    PLANET_PACK = "PLANET_PACK"
    GAME_OVER = "GAME_OVER"
    MENU = "MENU"


class BlindState(StrEnum):
    """Possible blind states during blind selection."""

    SELECT = "Select"
    UPCOMING = "Upcoming"
    CURRENT = "Current"
    SKIPPED = "Skipped"
    DEFEATED = "Defeated"


class CardFacing(StrEnum):
    """Card facing direction."""

    FRONT = "front"
    BACK = "back"


class Rarity(StrEnum):
    """Card rarity levels."""

    COMMON = "1"
    UNCOMMON = "2"
    RARE = "3"
    LEGENDARY = "4"

    @classmethod
    def from_int(cls, value: int) -> "Rarity":
        return cls(str(value))

    def display_name(self) -> str:
        names = {
            "1": "Common",
            "2": "Uncommon",
            "3": "Rare",
            "4": "Legendary",
        }
        return names[self.value]


class Card(BaseModel):
    """Representation of any card-like object (playing card, joker, consumable, etc.)."""

    type: str = Field(
        description="Card area/type (e.g., 'hand', 'joker', 'consumeable')"
    )
    name: str = Field(description="Display name of the card")
    main_description: str = Field(
        description="Primary description/effect text of the card"
    )
    secondary_description: Optional[str] = Field(
        default=None, description="Additional description/info text"
    )
    edition: Optional[str] = Field(
        default=None,
        description="Edition modifier (e.g., 'foil', 'holographic', 'polychrome', 'negative')",
    )
    enhancement: Optional[str] = Field(
        default=None,
        description="Enhancement modifier (e.g., 'Bonus Card', 'Mult Card', 'Wild Card', 'Glass Card', 'Steel Card', 'Stone Card', 'Gold Card', 'Lucky Card')",
    )
    seal: Optional[str] = Field(
        default=None,
        description="Seal modifier (e.g., 'Gold', 'Red', 'Blue', 'Purple')",
    )
    cost: Optional[int] = Field(default=None, description="Purchase cost in dollars")
    sells_for: Optional[int] = Field(default=None, description="Sell value in dollars")
    copy_compatible: Optional[str] = Field(
        default=None,
        description="Blueprint/Brainstorm compatibility status",
    )
    facing: Optional[str] = Field(
        default=None, description="Card facing direction ('front' or 'back')"
    )
    rarity: Optional[int] = Field(
        default=None,
        description="Rarity level (1=Common, 2=Uncommon, 3=Rare, 4=Legendary)",
    )


class HandLevel(BaseModel):
    """Level information for a poker hand type."""

    level: int = Field(description="Current level of the hand type")
    chips: int = Field(description="Base chips contributed by this hand type")
    mult: int = Field(description="Base multiplier for this hand type")
    times_played: int = Field(
        alias="times_played", description="Number of times this hand has been played"
    )


class Tag(BaseModel):
    """A tag that provides bonuses or effects."""

    name: str = Field(description="Display name of the tag")
    description: str = Field(description="Effect description of the tag")


class BlindInfo(BaseModel):
    """Information about a blind (Small, Big, or Boss)."""

    state: str = Field(
        description="Current state of the blind (Select, Upcoming, Current, Skipped, Defeated)"
    )
    chips_needed: int = Field(description="Chips required to defeat this blind")
    reward: int = Field(description="Dollar reward for defeating this blind")
    tag: Optional[str] = Field(
        default=None, description="Tag name awarded for skipping this blind"
    )
    tag_description: Optional[str] = Field(
        default=None, description="Description of the skip tag"
    )
    boss_description: Optional[str] = Field(
        default=None, description="Special effect description (Boss blind only)"
    )


class FailedAction(BaseModel):
    """Information about a failed action from the previous turn."""

    action: str = Field(description="The action that failed")
    positions: Optional[list[int]] = Field(
        default=None, description="Position arguments of the failed action"
    )
    reason: str = Field(description="Reason the action failed")


class PlayedHand(BaseModel):
    """Record of a previously played hand."""

    hand_name: str = Field(description="Type of hand played (e.g., 'Flush', 'Pair')")
    chips_earned: int = Field(description="Total chips earned from this hand")
    ante: int = Field(description="Ante number when the hand was played")
    blind: str = Field(description="Blind type when the hand was played")


class BlindsInfo(BaseModel):
    """Container for all blind information."""

    Small: BlindInfo = Field(description="Small blind info")
    Big: BlindInfo = Field(description="Big blind info")
    Boss: BlindInfo = Field(description="Boss blind info")


# Type aliases for card collections
CardList = Annotated[list[Card], Field(default_factory=list)]
HandLevels = dict[str, HandLevel]


class BaseGameState(BaseModel):
    """Base fields present in all game states."""

    state: GameState = Field(description="Current game phase/state")
    dollars: int = Field(description="Current money")
    max_jokers: int = Field(description="Maximum joker slots")
    max_consumeables: int = Field(description="Maximum consumable slots")
    ante: int = Field(description="Current ante number")
    played_hands: Optional[list[PlayedHand]] = Field(
        default=None, description="History of hands played this run"
    )
    jokers: CardList = Field(description="Currently owned jokers")
    consumeables: CardList = Field(description="Currently owned consumables")
    deck: CardList = Field(description="Cards remaining in the deck")
    hand_levels: HandLevels = Field(description="Level info for each poker hand type")
    tags: list[Tag] = Field(default_factory=list, description="Currently owned tags")
    owned_vouchers: list[str] = Field(
        default_factory=list, description="Keys of owned vouchers"
    )
    can_reroll_boss: bool = Field(
        default=False, description="Whether the boss blind can be rerolled"
    )
    failed_action: Optional[FailedAction] = Field(
        default=None, description="Info about failed action from previous turn"
    )


class SelectingHandState(BaseGameState):
    """State when player is selecting cards to play or discard."""

    state: Literal[GameState.SELECTING_HAND] = GameState.SELECTING_HAND
    hand: CardList = Field(description="Cards currently in hand")
    hands_left: int = Field(description="Remaining plays this round")
    discards_left: int = Field(description="Remaining discards this round")
    blind_info: BlindsInfo = Field(description="Information about all blinds")
    chips: int = Field(description="Chips earned so far this round")


class ShopState(BaseGameState):
    """State when player is in the shop between rounds."""

    state: Literal[GameState.SHOP] = GameState.SHOP
    shop_cards: CardList = Field(description="Cards available for purchase")
    shop_boosters: CardList = Field(description="Booster packs available for purchase")
    shop_vouchers: CardList = Field(description="Vouchers available for purchase")
    reroll_cost: int = Field(description="Cost to reroll the shop")


class BlindSelectState(BaseGameState):
    """State when player is selecting which blind to play or skip."""

    state: Literal[GameState.BLIND_SELECT] = GameState.BLIND_SELECT
    blind_info: BlindsInfo = Field(description="Information about all blinds")


class PackState(BaseGameState):
    """Base state for booster pack selection."""

    pack_choices: CardList = Field(
        description="Cards available to choose from the pack"
    )


class TarotPackState(PackState):
    """State when selecting from a tarot pack."""

    state: Literal[GameState.TAROT_PACK] = GameState.TAROT_PACK
    hand: CardList = Field(description="Cards currently in hand (for targeting)")


class SpectralPackState(PackState):
    """State when selecting from a spectral pack."""

    state: Literal[GameState.SPECTRAL_PACK] = GameState.SPECTRAL_PACK
    hand: CardList = Field(description="Cards currently in hand (for targeting)")


class StandardPackState(PackState):
    """State when selecting from a standard playing card pack."""

    state: Literal[GameState.STANDARD_PACK] = GameState.STANDARD_PACK


class BuffoonPackState(PackState):
    """State when selecting from a buffoon (joker) pack."""

    state: Literal[GameState.BUFFOON_PACK] = GameState.BUFFOON_PACK


class PlanetPackState(PackState):
    """State when selecting from a planet pack."""

    state: Literal[GameState.PLANET_PACK] = GameState.PLANET_PACK


class GameOverState(BaseGameState):
    """State when the game has ended."""

    state: Literal[GameState.GAME_OVER] = GameState.GAME_OVER
    best_hand: int = Field(description="Highest chips earned in a single hand")
    final_ante: int = Field(description="Final ante reached")
    final_round: int = Field(description="Final round reached")


class MenuState(BaseGameState):
    """State when at the main menu."""

    state: Literal[GameState.MENU] = GameState.MENU


class TransitionalState(BaseGameState):
    """State for transitional phases that don't require player input."""

    state: Literal[
        GameState.PLAY_TAROT,
        GameState.HAND_PLAYED,
        GameState.DRAW_TO_HAND,
        GameState.NEW_ROUND,
        GameState.ROUND_EVAL,
    ]


# Union type for all possible game states
AnyGameState = (
    SelectingHandState
    | ShopState
    | BlindSelectState
    | TarotPackState
    | SpectralPackState
    | StandardPackState
    | BuffoonPackState
    | PlanetPackState
    | GameOverState
    | MenuState
    | TransitionalState
)


def parse_game_state(data: dict) -> AnyGameState:
    """Parse a game state dictionary into the appropriate typed model.

    Args:
        data: Raw game state dictionary from the game.

    Returns:
        A typed game state model based on the 'state' field.

    Raises:
        ValueError: If the state type is unknown.
    """
    state_type = data.get("state")

    state_to_model: dict[str, type[BaseGameState]] = {
        GameState.SELECTING_HAND: SelectingHandState,
        GameState.SHOP: ShopState,
        GameState.BLIND_SELECT: BlindSelectState,
        GameState.TAROT_PACK: TarotPackState,
        GameState.SPECTRAL_PACK: SpectralPackState,
        GameState.STANDARD_PACK: StandardPackState,
        GameState.BUFFOON_PACK: BuffoonPackState,
        GameState.PLANET_PACK: PlanetPackState,
        GameState.GAME_OVER: GameOverState,
        GameState.MENU: MenuState,
    }

    transitional_states = {
        GameState.PLAY_TAROT,
        GameState.HAND_PLAYED,
        GameState.DRAW_TO_HAND,
        GameState.NEW_ROUND,
        GameState.ROUND_EVAL,
    }

    if state_type in state_to_model:
        return state_to_model[state_type].model_validate(data)
    elif state_type in transitional_states:
        return TransitionalState.model_validate(data)
    else:
        raise ValueError(f"Unknown game state type: {state_type}")
