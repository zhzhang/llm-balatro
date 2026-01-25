"""Prompt templates for the Balatro bot's post-game analysis."""


# =============================================================================
# ANTE SUMMARY PROMPTS
# =============================================================================
# Used by generate_ante_summary() to critique decisions made in each ante.


def build_ante_summary_prompt(
    ante_num: int, ante_history: str, later_summaries: str = ""
) -> str:
    """Build prompt for generating a summary of decisions made in a single ante.

    Args:
        ante_num: The ante number being summarized.
        ante_history: The complete history of turns in this ante.
        later_summaries: Optional summaries of later antes for context.

    Returns:
        The formatted prompt string.
    """
    context_section = ""
    if later_summaries:
        context_section = f"""For context, here are the summaries of the later antes that followed this one:

{later_summaries}

Use this context to understand how your decisions in Ante {ante_num} set up (or failed to set up) your later game.

"""

    return f"""Here is the complete history of Ante {ante_num}:

{ante_history}

{context_section}

Please briefly critique every decision you made in this ante. For each move:
1) Look at the resulting state after the move, and note any surprises or unexpected outcomes.
2) Examine chip scoring outcomes in subsequent turns and antes, and note whether the move was particularly impactful in a good or bad way.
3) State with a simple yes or no whether you would make the same decision again.
"""


# =============================================================================
# FINAL REFLECTION PROMPT
# =============================================================================
# Used by game_summary_prompt() for the end-of-game comprehensive reflection.


def build_final_reflection_prompt(
    game_plan: str, summaries_text: str, game_outcome: str, game_stats: str
) -> str:
    """Build the prompt for generating the final game reflection.

    Args:
        summaries_text: Combined text of all ante summaries.
        game_outcome: The outcome of the game (win/loss/etc).
        game_stats: Formatted string of game statistics.

    Returns:
        The formatted prompt string.
    """
    return f"""The game has ended. Here is your original strategy guide for the game:

{game_plan}

Here are your summaries from each ante of the game:

{summaries_text}

Game Outcome: {game_outcome}
{game_stats}

Based on these ante-by-ante notes, please create a comprehensive final reflection by writing the following four sections:

1. Clarifications of key game mechanics as a result of unexpected outcomes.

2. Best and worst decisions.

3. For worst decisions, state what you would do differently next time and why.

4. What parts of your strategy were successful and what parts were not?
"""


SYSTEM_PROMPT = """
# Game Overview
You are playing Balatro, a game based on poker that uses similar words as poker.
However, the actual game is very different from poker, so pay close attention to the following rules.
This system prompt describe the overall structure of the game.
Subsequently, you will be presented specific tasks to do, such as deciding on the next action to take, analyzing specific objects in the game, or summarizing your performance in a completed run.

In Balatro, the goal is to beat rounds and bosses by playing hands of cards to reach a certain total chips threshold to pass the round.
The game moves through three phases: Blind Select, Round, and Shop, which are described below.
Once you have beaten 8 boss rounds, you will win the game.

## Blind Select
In the Blind Select phase, you will choose which blind you will play, and you will receive a tag if you choose to skip the blind.
If you skip a blind, you will remain in the Blind Select phase to make the play vs skip decision about the next blind, and will not have the opportunity to shop.
Boss blinds cannot be skipped.
Blinds are organized into groups of three: Small, Big, and Boss, which together form a single Ante.
After beating the Boss Blind of an Ante, the Ante will increase, making the chips needed to pass each blind much higher.

## Round
In the Round phase, you will play hands of cards to reach the chips threshold.
You will have a limited number of hands and discards to reach the threshold.
You may select UP TO 5 cards to play or discard, per use of the "play" or "discard" commands. Using the "play" or "discard" commands consumes one of your remaining hands or discards, respectively.
The possible hand types are the classic poker hands, in order of increasing value: high card, pair, two pair, three of a kind, straight, flush, full house, four of a kind, straight flush, and royal flush.
In addition, there is potential to create special hands that don't exist in regular poker:
- five of a kind - five cards of the same rank
- flush house - a full house with all cards sharing the same suit
- flush five - five cards of the same rank and suit
The final chips you earn from playing a hand is the chips value types the mult value.
Each of the above hand types has a base chips and base mult value, determined by the current level of the hand type. This will be shown in the game state below.  

Then, special effects are applied that modify the base chips and mult value to the final chips and mult value.
Effects from any source, including cards, jokers, and boss effects, are applied in the following order:
1) Boss Blind effects activate first
2) 'On played' Jokers trigger (before scoring) - examples: Green Joker scaling, DNA
3) Played cards score left-to-right, each card triggering:
- Base chips
- Card modifiers (enhancements → seals → editions)
- 'On scored' Jokers (left-to-right for multiple Jokers)
- Retriggers (repeat the above sequence; red seal first, then retriggering Jokers left-to-right)
4) Held-in-hand abilities check left-to-right:
- Steel card enhancements
- 'On held' Jokers (Baron, Raised Fist, etc.) activate left-to-right
- Retriggers for held cards (red seal first, then Mime, etc.)
5) 'Independent' Jokers activate left-to-right (basic Joker, editions on Jokers)
6) Consumables (Observatory planets give x1.5 Mult)

All activations in each category are applied left-to-right.
Finally, the resulting chips and mult values and multiplied together to get the final amount of chips earned. If the total chips you've earned from all hands played during the round exceeds the threshold, you win the round.

Mult increases may be additive or multiplicative, depending on the source.
A + mult, for example +10, that adds 10 to the multiplier.
A x mult, for example x2, that multiplies the multiplier by 2.
To put this all tother, playing a pair of kings with a +10 mult and a x2 mult effect will give you
10 chips from the base chips, plus 10 more from each of the kings, for a total of 30 chips, times 2 base multiplier
+10 mult = 12 multiplier, times 2 x mult = 24 mult for a total of 720 chips for the hand.
IMPORTANT! The +chips values from cards selected to be played are ONLY COUNTED IF THE CARD IS PART OF THE HIGHEST HAND MADE BY THE CARDS PLAYED.
If the above example, if you play the same pair of kings plus an ace, only the pair of kings will add their chips to the score, and the ace will not contribute extra chips to the score because it does not participate in the king pair.
Crucially, cards that do not participate in the hand do not trigger any "when played" effects for themselves, or other effects.

At the end of a round, you will earn $1 for each remaining hand, and you will earn an additional $1 of interest for each $5 you have at the end of the round.
When a round is won, you will automatically advance to the SHOP phase.

## Shop
In the shop, you will be able to buy jokers, cards, consumeables, and booster packs to help you in the game.
Planet cards level up their corresponding hand types, increasing the base chips and mult value of the hand type.

## Inventory
Your inventory is composed of jokers, consumables, and vouchers.
Joker effects are active at all times.
Consumables have a one-time effect when used, and permanently modify hand level, deck cards, and jokers, and disappear from your inventory after use.
Jokers and consumables have a maximum capacity given by the Max Jokers and Max Consumables settings in the game state.
If you see an error saying that you cannot select or buy a joker or consumable, it is because you have reached the maximum capacity for that type of card.
You may sell a joker or consumable or use the cost of a joker or consumable to make space for a new one.

## IMPORTANT! Special Effects Always Override Basic Rules
The effects written in the text of any cards, jokers, or boss effects in play will override any of the basic rules stated below.

# Game Keywords
Debuffed - A card or joker that has been debuffed has its abilities and chip values disabled. However, it WILL still participate in forming a hand type, and the remaining played cards as well as base mult and joker effects will STILL CONTRIBUTE TO THE CHIPS EARNED.
Contains - A scored hand still contains another hand type of the other hand type can be formed with the cards in the hand. For example, a full house contains a two pair, and a five of a kind contains a four of a kind.
In hand/Stays in hand - These abilities trigger when a hand is played, and the card remains unplayed in hand rather than being among the selected played cards.
Enhancement/Enhanced Card - Enhancements apply only to playing cards, not jokers. Possible enhancements are: Bonus Card, Mult Card, Wild Card, Glass Card, Steel Card, Stone Card, Gold Card, Lucky Card. Any effects from tarot or joker cards that say "becomes" or "turns into" or "enhances" will convert the affected playing cards into the enhanced card type.
Editions/Card Edition - Editions apply to both playing cards and jokers. Possible editions are: Base, Foil, Holographic, Polychrome, Negative.
"""
# Command descriptions keyed by action name for dynamic inclusion
COMMAND_DESCRIPTIONS = {
    # Blind Select
    "play_round": "play_round - Play the current round.",
    "skip_round": "skip_round - Skip the current round. Boss blinds cannot be skipped.",
    "reroll_boss": "reroll_boss - Reroll the boss blind. Will cost $10.",
    # Round
    "play": "play <card1> <card2> ... <card5> - Play the selected cards and draw new ones from the deck. You may play up to 5 cards at a time. If you play a hand, you must also respond with the intended hand type you think you are playing, and an estimate of the number of chips you think you will earn from the hand. Use the results of previous hands played to inform your estimate.",
    "discard": "discard <card1> <card2> ... <card5> - Discard the selected cards and draw new ones from the deck. You may discard up to 5 cards at a time.",
    # Shop
    "buy_card": "buy_card <card_position> - Buy a card from the card section. Individual Joker cards are also bought from the card section.",
    "buy_booster": "buy_booster <booster_pack_position> - Buy a booster pack from the booster pack section.",
    "buy_voucher": "buy_voucher <voucher_position> - Buy a voucher from the voucher section.",
    "buy_and_use_consumable": "buy_and_use_consumable <consumable_position> - Buy a consumable type card (Tarot, Planet, Spectral) from the card section and use it immediately. Cannot do this if the consumable requires target hand cards.",
    "reroll_shop": "reroll_shop - Spends the reroll cost to reroll the cards section of the shop.",
    "round_select": "round_select - Finish shopping and go to the round select screen.",
    # Booster Pack
    "select": "select <pack_card_position> <hand_card_position1> <hand_card_position2> ... <hand_card_positionN> - Select a card from the booster pack. The hand card positions may be required depending on if the booster pack card selected needs targets. In 'Mega' booster packs that say 'choose 2 of N', make the selections one at a time. If you intend to select cards 1 and 3 for example, issue a 'select 1' command, then a 'select 2' command, because the 3rd card position will become the second position after selecting the first card.",
    "skip_booster": "skip_booster - Skip the remaining selections in the current booster pack.",
    # Hand Management
    "rearrange_hand": "rearrange_hand <card1> <card2> ... <cardN> - Rearrange the hand of cards. Every index in the list of current cards must be present, i.e. if there are 5 cards, the indices 1-5 must be present.",
    # Consumables
    "use_consumable": "use_consumable <consumeable_position> <target_card_position1> <target_card_position2> ... <target_card_positionN> - Use a consumeable from the consumeables section. The first position argument is the position within your consumables inventory of the consumable you'd like to use. Subsequent position arguments specify the cards in hand that the consumeable will be used on, if that consumeable requires targets.",
    "sell_consumable": "sell_consumable <consumeable_position> - Sell a consumeable from the consumeables section.",
    # Jokers
    "rearrange_jokers": "rearrange_jokers <joker1> <joker2> ... <jokerN> - Rearrange the list of currently owned jokers. Every index in the list of current jokers must be present, i.e. if there are 5 jokers, the indices 1-5 must be present.",
    "sell_joker": "sell_joker <joker_position> - Sell a joker from the jokers section.",
}

MANUAL_STRATEGY_PROMPT = """
This strategy is handwritten by a human expert player of Balatro. Follow it precisely for the best chance of winning.

# Absolute Rules!!!
- Always always always try to force a flush. Do not try to play any other type of hand, unless it is a higher flush type like flush five or flush house.
- IF YOU HAVE A FLUSH ALREADY, PLAY IT IMMEDIATELY. DO NOT WAIT TO PLAY IT.
- Aggressively use discards to draw a flush. Pick one suit in hand to build a flush around, and discard ALL other cards of ALL other suits, even if they are also close to a flush.
- When discarding, never discard less than 4 cards. NEVER DISCARD LESS THAN 3 CARDS! After you decide which suit you are building a flush around, YOU MUST DISCARD ALL OTHER CARDS OF ALL OTHER SUITS.
- I REPEAT NEVER DISCARD LESS THAN FOUR CARDS. DISCARD ALL CARDS THAT DON'T BELONG TO THE SUIT YOU ARE BUILDING A FLUSH AROUND. ALL MEANS ALL. DISCARD ALL CARDS THAT DON'T BELONG TO THE SUIT YOU ARE BUILDING A FLUSH AROUND.
- If you have no discards left and don't have a flush in hand, treat your remaining hands as discards and cycle out as many cards as you can to find a flush.
- Never sell a joker to leave an empty slot unless you are preparing to immediately replace it with a better joker on your next tur.
- Always rearrange your jokers so that jokers that Add (+) mult are on the left, and jokers that Multiply (x) mult are on the right. NOT REARRANGE YOUR JOKERS THIS WAY WILL LEAD TO EXPONENTIALLY WORSE SCORES.
- ALWAYS CONSIDER REARRANGING YOUR JOKERS BEFORE YOU SELECT "play_round" TO MAXIMIZE YOUR CHANCES OF BEATING THE ROUND.
- Cards in your hand are always sorted by suit. For boss blinds that draw cards face down, you may use your knowledge about your previous hand, previous action taken, and remaining cards in your deck to infer which cards are which suit.
- NEVER HOLD A PLANET CARD IN YOUR INVENTORY UNUSED. USE ALL PLANET CARDS IMMEDIATELY.

# Economy
You earn more than the reward for each blind:
- You earn $1 for each remaining hand, so try to beat each blind by playing as few hands as possible. Aggressively use discards to accomplish this, as you get nothing for remaining discards.
- You earn $1 of interest for each $5 you have at the end of the round, up to $5. Build up to $25 as fast as possible.

# Tags
- Always skip blinds for the Negative tag.
- If you have < $15, you should skip blind for the Polychrome, Rare, or Investment tags.
- No other tag is worth skipping a blind for, because skipping a blind means you cannot shop until you beat the next blind.

# Joker Build Strategy
- In the early game, find one joker that adds +chips, and one that adds +mult. It is VERY IMPORTANT to have one of each type!
- Starting from Ante 3, buy X-mult jokers to build around.
- Whenever you are in the shop and have an X-mult joker in your inventory already, consider whether any new jokers

# Voucher Strategy
- Always buy the Hieroglyph voucher if you can afford it.
- Buy Grabber, Wasteful, Recyclomancy, Reroll Surplus, Paint Brush, Palette, Telescope, Directors Cut, and Seed Money vouchers if you can afford them and ONLY if there is no key uncommon or rare jokers to buy. No other voucher is worth it.

# Tarot strategy
- First priority: pick a suit based on your owned jokers and use either Star (Diamonds), Moon (Clubs), Sun (Hearts), or World (Spades) to convert the rest of your deck to that suit. Make the majority of your deck a single chosen suit.
- Second priority: thin the deck towards the suit you picked above, using Hanged Man and Death.
- Third priority: use Hermit and Temperance to generate cash.
- Fourth priority: created enhanced cards in the suit you picked above, with the following priority: wild, steel, glass, mult, bonus, lucky, gold.

# Ante by Ante Strategy
## Antes 1-2 Early set up for later scaling
- In the first ante, always try to force a flush. Do not try to play any other type of hand. A flush is the most reliable way to win in 1-2 hands and maximize the $ you earn by not playing all of your hands.
- Highest priority shop wise is to buy jokers that have stacking scaling with synergy with playing a single hand type: flush. Examples are Supernova, Fortune Teller, Constellation, Hiker, Lucky Cat,  
- If offered the opportunity, buy key X-mult jokers or "copy" ability jokers. Don't reroll to find them just yet. Especially buy anything that gives X-mult for a particular suit.
- Buy any joker that reliably gives a fixed amount of +chips or +mult.
- You may reroll to achieve the above two joker purchases if you have > $25.
- Then, fill out any joker slots with any jokers you see that give +chips or +mult, so as to have 5 jokers going into Ante 3. Do this even if the jokers are only temporary, like Popcorn.
- Don't buy planet or tarot packs unless you have > $30 and there is nothing else to buy.
- If nothing in the shop meets the above criteria, save your money and play the next round, as you earn interest on every $5 you have. Do not reroll the shop.
- After meeting all of the above, build up to $25 as fast as possible so that you are making the maximum amount of interest possible.

## Antes 3-8 Scale up
- Look for jokers that give X-mult in order to scale to the last two antes. If you do not have space to add an available X-mult joker, sell your worst +chips or +mult joker. You should spend down your money for the right X-mult joker if you see it.
- Look for jokers that have "copy" abilities, as these are particularly valuable at this point to copy a key X-mult joker for quadratic scaling. As above, sell +mult and +chips jokers to make space for these, and spend down your money for the right copy joker if you see it.
- If neither of the above are available, if you have any empty joker slots, fill them with the best +chips and +mult jokers you can find without rerolling.
- Except for the above joker purchases, which you should spend down your money for, you should maintain cash above $15 every turn.
- Begin using Tarot packs to make an ideal deck: pick one suit and use tarot cards to conver the rest of your deck to that suit. That includes using Hanged Man to destroy cards, Death to turn cards into other cards, using the suit convert tarots, and creating wild cards that represent any suit with tarots. If you have the Fortune Teller joker, prioritize this piece of the strategy because each tarot card used adds +mult to Fortune Teller.
- If none of the above exist in the shop, you may reroll your shop as long as you have > $20 after the reroll.
- If none of the above applies, buy Planet cards and packs and scale the flush hand type.
- If you have the Telescope voucher, you should buy as many planet packs as possible, as they will each be able to upgrade flush.
- When you reach Ante 7, start selling any jokers that do not contribute directly to chips or mult, and replacing them with jokers that do.
"""

SHOP_PROMPT = """
Consider the following when shopping, or picking cards from a booster pack:
- What synergies does the purchase or booster pack card have with inventory items you already have?
"""


# =============================================================================
# INITIAL GAME OBJECT ANALYSIS PROMPTS
# =============================================================================
# Used by _analyze_new_game_object() in bot_action.py to generate first impressions
# of game objects when they are first encountered (before playing with them).


def build_initial_boss_blind_analysis_prompt(object_name: str, description: str) -> str:
    """Build prompt for analyzing a boss blind based on its description alone.

    Args:
        object_name: Name of the boss blind.
        description: The boss blind's effect description.

    Returns:
        The formatted prompt string.
    """
    return f"""You are providing an initial analysis of the boss blind **{object_name}** in Balatro, based on its effect description alone (before facing it).

## Boss Blind Effect

{description}

Based on this effect, provide:

1. **Effect Analysis**: What does this boss blind's effect do and how will it constrain gameplay?

2. **Counter Strategies**: What items, hand types, or approaches might work well against this effect?

3. **Risks**: What strategies or items might struggle against this boss blind?

4. **Initial Assessment**: How difficult is this boss blind likely to be?

Keep the analysis focused and concise (2-3 paragraphs). This is your initial impression before facing the boss blind."""


def build_initial_item_analysis_prompt(
    object_name: str, object_type: str, description: str
) -> str:
    """Build prompt for analyzing an item based on its description alone.

    Args:
        object_name: Name of the item.
        object_type: Type of the item (e.g., "joker", "consumable", "voucher", "tag").
        description: The item's description text.

    Returns:
        The formatted prompt string.
    """
    return f"""You are providing an initial analysis of **{object_name}** ({object_type}) in Balatro, based on its description alone (before any play with it has occurred).

## Description

{description}

Based on this description, provide:

1. **Potential Impact**: What effect should this have on scoring or gameplay?

2. **Synergies**: What other items or strategies might this work well with?

3. **Timing**: At what ante stages or game phases would this be most valuable?

4. **Initial Assessment**: Based on the description, is this likely a must-pick, situational, or skip?

Keep the analysis focused and concise (2-3 paragraphs). This is your initial impression before playing with it."""


# =============================================================================
# POST-GAME OBJECT ANALYSIS PROMPTS
# =============================================================================
# Used by _analyze_game_object() in postgame_analysis.py to generate analysis
# based on actual play data from a completed run.


def build_postgame_boss_blind_analysis_prompt(
    object_name: str, hands_text: str, previous_section: str = ""
) -> str:
    """Build prompt for analyzing a boss blind based on play data.

    Args:
        object_name: Name of the boss blind.
        hands_text: Formatted string of all hands played during the run.
        previous_section: Optional section with previous analysis to consider.

    Returns:
        The formatted prompt string.
    """
    return f"""You are analyzing the boss blind **{object_name}** from a completed Balatro run.

Below is the complete trajectory of all hands played during this run. Examine how the boss blind's effect impacted gameplay and scoring.

## All Hands Played

{hands_text}
{previous_section}
Based on this data, analyze how to beat {object_name}:

1. **Effect Impact**: How did this boss blind's special effect constrain or affect gameplay?

2. **Successful Strategies**: What items, hand types, or strategies were effective against it?

3. **Common Pitfalls**: What approaches struggled or failed against this blind?

4. **Overall Strategy**: What's the recommended approach for beating this boss blind?

Keep the analysis focused and concise (2-3 paragraphs). Be specific with numbers from the data."""


def build_postgame_item_analysis_prompt(
    object_name: str, object_type: str, hands_text: str, previous_section: str = ""
) -> str:
    """Build prompt for analyzing an item based on play data.

    Args:
        object_name: Name of the item.
        object_type: Type of the item (e.g., "joker", "consumable", "voucher").
        hands_text: Formatted string of all hands played during the run.
        previous_section: Optional section with previous analysis to consider.

    Returns:
        The formatted prompt string.
    """
    return f"""You are analyzing the impact of **{object_name}** ({object_type}) from a completed Balatro run.

Below is the complete trajectory of all hands played during this run. Examine when {object_name} appears and how it affected chip scoring.

## All Hands Played

{hands_text}
{previous_section}
Based on this data, analyze the impact of {object_name}:

1. **Chip Impact**: Looking at hands where {object_name} was present/used, how did it affect scoring?

2. **Synergies**: What other items was it commonly paired with? Which combinations seemed effective?

3. **Timing**: At what ante stages did it appear most valuable?

4. **Overall Assessment**: Is this item a must-pick, situational, or skip?

Keep the analysis focused and concise (2-3 paragraphs). Be specific with numbers from the data."""


# =============================================================================
# GAME PLAN GENERATION PROMPT
# =============================================================================
# Used by generate_game_plan() in bot_action.py to synthesize learnings from
# past runs into a strategic guide for the upcoming run.


def build_game_plan_prompt(reflections_text: str, card_reference: str) -> str:
    """Build the prompt for generating a game plan from past reflections.

    Args:
        reflections_text: Combined text of reflections from all past games.
        card_reference: Formatted string of all card reference data.

    Returns:
        The formatted prompt string.
    """
    return f"""You are about to play a new game of Balatro.
Here are your reflections and outcomes from all previous games:

{reflections_text}

Here is a list of all jokers, vouchers, tarot cards, spectral cards, boss blinds, and chip requirements in the game to help you plan your strategy:

{card_reference}

Based on these past experiences and the card reference above, please create a detailed game guide for your upcoming run. Write three sections:

1. Clarifications of key game mechanics as a result of unexpected outcomes.

2. A list of absolute do's and don'ts for the upcoming run that apply regardless of what happens in the run.

3. Ante-by-ante strategy with guidelines for each ante. Do not mention specific turn numbers, only ante numbers.

Make sure your guide is detailed and actionable - it will be referenced throughout your run."""


# =============================================================================
# SYSTEM PROMPT FORMATTING
# =============================================================================
# Helper functions for building the complete system prompt with dynamic sections.


def format_game_plan_section(game_plan: str) -> str:
    """Format the game plan section to be appended to the system prompt.

    Args:
        game_plan: The strategic guide text generated from past reflections.

    Returns:
        The formatted section to append to the system prompt.
    """
    return f"""

# Guide for This Run
The following is your strategic guide generated from all past game reflections and outcomes. Use this to inform your decisions:

{game_plan}
"""
