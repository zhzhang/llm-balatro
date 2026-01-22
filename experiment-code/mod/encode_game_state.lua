utils = require('utils')

-- Track previous state for calculating chips earned
local last_encoded_state = nil
local chips_before_hand = nil

function Game:add_hand_to_state(state)
    local cards = {}
    for i, card in pairs(G.hand.cards) do
        cards[i] = get_card_repr(card)
    end
    state.hand = cards
end

function Game:add_plays_discards_to_state(state)
    state.hands_left = G.GAME.current_round.hands_left
    state.discards_left = G.GAME.current_round.discards_left
end

function Game:add_jokers_to_state(state)
    local jokers = {}
    for i, joker in pairs(G.jokers.cards) do
        jokers[i] = get_card_repr(joker)
    end
    state.jokers = jokers
end

function Game:add_consumeables_to_state(state)
    local consumeables = {}
    for i, consumeable in pairs(G.consumeables.cards) do
        consumeables[i] = get_card_repr(consumeable)
    end
    state.consumeables = consumeables
end

function recursively_build_text_field(table)
    if not table or table.bot_seen then
        return ""
    end
    table.bot_seen = true
    acc = ""
    for k, v in pairs(table) do
        if type(v) == 'table' then
            acc = acc .. " " .. recursively_build_text_field(v)
        end
        if k == 'text' then
            acc = acc .. " " .. v
        end
    end
    -- Strip spaces from leading and trailing edges
    acc = acc:gsub("^%s*(.-)%s*$", "%1")
    table.bot_seen = nil
    return acc
end

function get_ability_description(ability_table)
    return recursively_build_text_field(ability_table.main), recursively_build_text_field(ability_table.info)
end

function get_shop_objects(objects)
    local object_reprs = {}
    for i, object in pairs(objects) do
        object_reprs[i] = get_card_repr(object)
    end
    return object_reprs
end

function get_card_repr(card)
    ability_table = card:generate_UIBox_ability_table()
    main_desc, secondary_desc = get_ability_description(ability_table)
    name = (card.label == "Stone Card" and "Stone Card") or (card.rank and card.base.name) or card.label
    repr = {
        type = card.area.config.type,
        name = name,
        main_description = main_desc,
        secondary_description = secondary_desc,
        edition = (card.edition or {}).type,
        enhancement = (card.ability or {}).name,
        seal = (card.seal or {}).type,
        cost = card.cost,
        sells_for = card.sell_cost,
        copy_compatible = card.ability.blueprint_compat,
        facing = card.facing,
        rarity = card.config and card.config.center and card.config.center.rarity,
    }
    return repr
end

function Game:add_pack_choices_to_state(state)
    local pack_choices = {}
    for i, card in pairs(G.pack_cards.cards) do
        pack_choices[i] = get_card_repr(card)
        if card.label == "Misprint" then
            pack_choices[i].description = "When a hand is played, randomly contribute between +0 and +23 Mult, inclusive."
        end
    end
    state.pack_choices = pack_choices
end

function Game:add_blind_info_to_state(state)
    blind_info = {}
    for blind_name, blind_state in pairs(G.GAME.round_resets.blind_states) do
        tag = G.GAME.round_resets.blind_tags[blind_name]
        local blind_choice = {
          config = G.P_BLINDS[G.GAME.round_resets.blind_choices[blind_name]],
        }
        local blind_amt = get_blind_amount(G.GAME.round_resets.blind_ante)*blind_choice.config.mult*G.GAME.starting_params.ante_scaling
        blind_info[blind_name] = {
            state = blind_state,
            chips_needed = blind_amt,
            reward = blind_choice.config.dollars,
        }
        if tag then
            tag_obj = Tag(tag, nil, blind_choice)
            dummy_arg = {}
            tag_obj:get_uibox_table(dummy_arg)
            blind_info[blind_name].tag = G.P_TAGS[tag].name
            main, secondary = get_ability_description(dummy_arg.ability_UIBox_table)
            blind_info[blind_name].tag_description = main
            -- blind_info[blind_name].tag_secondary_description = secondary
        end
        if blind_name == 'Boss' then
            local loc_target = localize{type = 'raw_descriptions', key = blind_choice.config.key, set = 'Blind', vars = {localize(G.GAME.current_round.most_played_poker_hand, 'poker_hands')}}
            boss_description = ""
            for i, line in pairs(loc_target) do
                boss_description = boss_description .. line
                if i < #loc_target then
                    boss_description = boss_description .. " "
                end
            end
            blind_info[blind_name].boss_description = boss_description
        end
    end
    state.blind_info = blind_info
end

function Game:add_deck_to_state(state)
    local deck = {}
    for i, card in pairs(G.deck.cards) do
        deck[i] = get_card_repr(card)
    end
    state.deck = deck
end

function Game:add_can_reroll_boss_to_state(state)
    if ((G.GAME.dollars-G.GAME.bankrupt_at) - 10 >= 0) and
      (G.GAME.used_vouchers["v_retcon"] or
      (G.GAME.used_vouchers["v_directors_cut"] and not G.GAME.round_resets.boss_rerolled)) then
        state.can_reroll_boss = true
    else
        state.can_reroll_boss = false
    end
end

function Game:add_hand_levels_to_state(state)
    local hand_levels = {}
    for hand_name, hand_data in pairs(G.GAME.hands) do
        hand_levels[hand_name] = {
            level = hand_data.level,
            chips = hand_data.chips,
            mult = hand_data.mult,
            times_played = hand_data.played,
        }
    end
    state.hand_levels = hand_levels
end

function Game:add_tags_to_state(state)
    local tags = {}
    for i, tag in ipairs(G.GAME.tags) do
        local dummy_arg = {}
        tag:get_uibox_table(dummy_arg)
        local main_desc, secondary_desc = get_ability_description(dummy_arg.ability_UIBox_table)
        tags[i] = {
            name = tag.name,
            description = main_desc,
        }
    end
    state.tags = tags
end

function Game:add_owned_vouchers_to_state(state)
    local owned_vouchers = {}
    for voucher_key, _ in pairs(G.GAME.used_vouchers) do
        table.insert(owned_vouchers, voucher_key)
    end
    state.owned_vouchers = owned_vouchers
end

function Game:encode_state()
    local state = {
        dollars = G.GAME.dollars,
        max_jokers = G.jokers.config.card_limit,
        max_consumeables = G.consumeables.config.card_limit,
        ante = G.GAME.round_resets.ante,
        round_number = G.GAME.round,
        seed = G.GAME.pseudorandom.seed,
        played_hands = G.PLAYED_HANDS,
    }

    Game:add_jokers_to_state(state)
    Game:add_consumeables_to_state(state)
    Game:add_deck_to_state(state)
    Game:add_hand_levels_to_state(state)
    Game:add_tags_to_state(state)
    Game:add_owned_vouchers_to_state(state)
    if self.STATE == self.STATES.SELECTING_HAND then
        state.state = 'SELECTING_HAND'
        Game:add_hand_to_state(state)
        Game:add_plays_discards_to_state(state)
        Game:add_blind_info_to_state(state)
        state.chips = G.GAME.chips
        state.boss_blind_disabled = G.GAME.blind and G.GAME.blind.disabled or false
        -- Add forced card index for Cerulean Bell
        if G.GAME.blind.name == 'Cerulean Bell' then
            for i, card in ipairs(G.hand.cards) do
                if card == G.FORCED_CARD then
                    state.forced_card_index = i
                    break
                end
            end
        end
    end
    if self.STATE == self.STATES.SHOP then 
        state.state = 'SHOP'
        state.shop_cards = get_shop_objects(G.shop_jokers.cards)
        state.shop_boosters = get_shop_objects(G.shop_booster.cards)
        state.shop_vouchers = get_shop_objects(G.shop_vouchers.cards)
        state.reroll_cost = G.GAME.current_round.reroll_cost
    end
    if self.STATE == self.STATES.PLAY_TAROT then 
        state.state = 'PLAY_TAROT'
    end
    if self.STATE == self.STATES.HAND_PLAYED then 
        state.state = 'HAND_PLAYED'
    end
    if self.STATE == self.STATES.DRAW_TO_HAND then 
        state.state = 'DRAW_TO_HAND'
    end
    if self.STATE == self.STATES.NEW_ROUND then
        state.state = 'NEW_ROUND'
    end
    if self.STATE == self.STATES.BLIND_SELECT then
        state.state = 'BLIND_SELECT'
        Game:add_blind_info_to_state(state)
    end
    if self.STATE == self.STATES.ROUND_EVAL then
        state.state = 'ROUND_EVAL'
    end
    if self.STATE == self.STATES.TAROT_PACK then
        state.state = 'TAROT_PACK'
        Game:add_hand_to_state(state)
    end
    if self.STATE == self.STATES.SPECTRAL_PACK then
        state.state = 'SPECTRAL_PACK'
        Game:add_hand_to_state(state)
    end
    if self.STATE == self.STATES.STANDARD_PACK then
        state.state = 'STANDARD_PACK'
    end
    if self.STATE == self.STATES.BUFFOON_PACK then
        state.state = 'BUFFOON_PACK'
    end
    if self.STATE == self.STATES.PLANET_PACK then
        state.state = 'PLANET_PACK'
    end
    if self.STATE == self.STATES.GAME_OVER then
        state.state = 'GAME_OVER'
        state.best_hand = G.GAME.round_scores.hand.amt
        state.final_ante = G.GAME.round_scores.furthest_ante.amt
        state.final_round = G.GAME.round_scores.furthest_round.amt
    end
    if self.STATE == self.STATES.MENU then
        state.state = 'MENU'
    end
    if string.find(state.state, 'PACK') then
        Game:add_pack_choices_to_state(state)
    end

    Game:add_can_reroll_boss_to_state(state)

    -- Store this state for next encode call
    last_encoded_state = state
    state.failed_action = G.bot_failed_action

    return state
end