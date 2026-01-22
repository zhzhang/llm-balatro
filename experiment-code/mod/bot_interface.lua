utils = require('utils')
local json = require "json"
local http = require("socket.http")
local ltn12 = require("ltn12")

-- Global state for non-blocking input
G.BOT_WAITING_FOR_INPUT = false
G.count_sent = 0
G.LAST_SENT_STATE = nil
G.BOT_SEND_DELAY_START = nil
G.BOT_SCREENSHOT_CAPTURED = false
G.BOT_POLL_LAST_TIME = nil
G.BOT_POLL_INTERVAL = 5  -- Poll every 5 seconds

-- Helper function for deep equality comparison
function tables_equal(t1, t2)
    if type(t1) ~= type(t2) then return false end
    if type(t1) ~= "table" then return t1 == t2 end
    
    for k, v in pairs(t1) do
        if not tables_equal(v, t2[k]) then return false end
    end
    for k, v in pairs(t2) do
        if t1[k] == nil then return false end
    end
    return true
end

function request_bot_action()
    -- Should not send state if there are event or state changes pending.
    should_send_state = true
    for k, v in pairs(G.E_MANAGER.queues.base) do
        if v.blocking then
            should_send_state = false
        end
    end
    if not G.STATE_COMPLETE then
        should_send_state = false
    end

    -- Handle any actions that should automatically be taken
    -- - Cashing out at the end of the round
    if should_send_state and G.STATE == G.STATES.ROUND_EVAL then
        G.FUNCS.cash_out(G.CASH_OUT_NODE)
        return
    end

    if G.STATE == G.STATES.GAME_OVER then
        should_send_state = true
    end

    if should_send_state and not G.BOT_WAITING_FOR_INPUT then
        -- Initialize delay timer if not set
        if not G.BOT_SEND_DELAY_START then
            G.BOT_SEND_DELAY_START = love.timer.getTime()
            G.BOT_SCREENSHOT_CAPTURED = false
        end
        
        local elapsed = love.timer.getTime() - G.BOT_SEND_DELAY_START
        
        -- After 1 second: capture screenshot (if not already done)
        -- This gives the game time to fully render before capturing.
        if elapsed >= 1 and not G.BOT_SCREENSHOT_CAPTURED then
            -- Capture screenshot. Note: love.graphics.captureScreenshot is async
            -- and only writes the file at the END of the current frame.
            love.graphics.captureScreenshot("bot_screenshot.png")
            G.BOT_SCREENSHOT_CAPTURED = true
        end
        
        -- After 2 seconds: send state (screenshot will be written by now)
        if elapsed >= 2 then
            G.BOT_SEND_DELAY_START = nil  -- Reset for next time
            G.BOT_SCREENSHOT_CAPTURED = false
            send_state()
        end
    else
        -- Reset delay timer if conditions are not met
        G.BOT_SEND_DELAY_START = nil
        G.BOT_SCREENSHOT_CAPTURED = false
    end

    poll_action()
end

-- Screenshot path that Python will read from
local SCREENSHOT_PATH = love.filesystem.getSaveDirectory() .. "/bot_screenshot.png"

function send_state()
    state = G:encode_state()

    -- Check if state is the same as last sent state
    if G.LAST_SENT_STATE and tables_equal(state, G.LAST_SENT_STATE) then
        return
    end
    
    -- Screenshot is captured at the start of the delay in request_bot_action(),
    -- NOT here, because love.graphics.captureScreenshot is async and only writes
    -- at the end of the frame. Capturing during the delay ensures it's ready.
    
    -- POST state to server - the server will process async and we'll poll for result
    local resp = http.request(
        "http://localhost:7777/state",
        json.encode(state)
    )
    
    G.BOT_WAITING_FOR_INPUT = true
    G.LAST_SENT_STATE = state
    G.count_sent = G.count_sent + 1
    G.BOT_POLL_LAST_TIME = nil  -- Reset poll timer to start polling immediately
end

function send_win_notification()
    -- Send a simple notification to the server that the game was won
    local win_data = {
        event = "game_won",
        ante = G.GAME.round_resets.ante,
        round = G.GAME.round,
        seed = G.GAME.pseudorandom.seed
    }
    
    -- POST win notification to server (fire and forget)
    local resp = http.request(
        "http://localhost:7777/game/win",
        json.encode(win_data)
    )
end

function poll_action()
    -- Poll the /action endpoint to check for pending actions
    if not G.BOT_WAITING_FOR_INPUT then
        return
    end
    
    -- Rate limit polling to once per second
    local current_time = love.timer.getTime()
    if G.BOT_POLL_LAST_TIME and (current_time - G.BOT_POLL_LAST_TIME) < G.BOT_POLL_INTERVAL then
        return
    end
    G.BOT_POLL_LAST_TIME = current_time
    
    -- Make GET request to /action endpoint
    local response_body = {}
    local result, status_code = http.request{
        url = "http://localhost:7777/action",
        method = "GET",
        sink = ltn12.sink.table(response_body)
    }
    
    if status_code ~= 200 then
        print("Error polling action: " .. tostring(status_code))
        return
    end
    
    local response_text = table.concat(response_body)
    local success, response = pcall(json.decode, response_text)
    
    if not success then
        print("Error decoding action response: " .. tostring(response))
        return
    end
    
    if response.status == "ready" then
        G.BOT_WAITING_FOR_INPUT = false
        handle_action(response)
    end
    -- If status is "pending", just continue polling
end

function select_cards(positions)
    -- First deselect all cards
    G.hand:unhighlight_all()
    for _, idx in pairs(positions) do
        if not G.hand.cards[idx].highlighted then
            G.hand:add_to_highlighted(G.hand.cards[idx])
        end
    end
end

function has_value(tab, val)
    for _, value in ipairs(tab) do
        if value == val then
            return true
        end
    end
    return false
end

function can_select_card(card)
    if card.ability.set == 'Joker' then
        if (card.edition and card.edition.negative) or #G.jokers.cards < G.jokers.config.card_limit then 
            return true
        end
    else
        return card:can_use_consumeable()
    end
    return false
end

function can_buy(card)
    if (card.cost > G.GAME.dollars - G.GAME.bankrupt_at) and (card.cost > 0) then
        return false
    end
    return true
end

function add_failed_action(action, reason)
    G.bot_failed_action = {
        action = action,
        reason = reason,
    } 
end


function handle_action(action)
    if action.action == "invalid" then
        -- Bot failed to parse action, resend state
        print("Bot returned invalid action, resending state")
        G.LAST_SENT_STATE = nil  -- Clear last sent state to force resend
        send_state()
        return
    elseif action.action == "play" then
        select_cards(action.positions)
        G.FUNCS.play_cards_from_highlighted()
    elseif action.action == "discard" then
        select_cards(action.positions)
        G.FUNCS.discard_cards_from_highlighted()
    elseif action.action == "buy_card" then
        card = G.shop_jokers.cards[action.positions[1]]
        if not card then
            add_failed_action(action, "No card at shop position " .. action.positions[1])
            send_state()
            return
        end
        if not G.FUNCS.check_for_buy_space(card) then
            add_failed_action(action, "Cannot buy card at position " .. action.positions[1])
            send_state()
            return
        end
        if not can_buy(card) then
            add_failed_action(action, "Cannot buy card at position " .. action.positions[1])
            send_state()
            return
        end
        G.FUNCS.buy_from_shop(card.children.buy_button.definition)
    elseif action.action == "buy_booster" then
        booster = G.shop_booster.cards[action.positions[1]]
        if not booster then
            add_failed_action(action, "No booster at position " .. action.positions[1])
            send_state()
            return
        end
        if not can_buy(booster) then
            add_failed_action(action, "Cannot open booster at position " .. action.positions[1])
            send_state()
            return
        end
        G.FUNCS.use_card(booster.children.buy_button.definition)
    elseif action.action == "buy_voucher" then
        voucher = G.shop_vouchers.cards[action.positions[1]]
        if not voucher then
            add_failed_action(action, "No voucher at position " .. action.positions[1])
            send_state()
            return
        end
        if not can_buy(voucher) then
            add_failed_action(action, "Cannot redeem voucher at position " .. action.positions[1])
            send_state()
            return
        end
        G.FUNCS.use_card(voucher.children.buy_button.definition)
    elseif action.action == "select" then
        local pack_card = G.pack_cards.cards[action.positions[1]]
        if not pack_card then
            add_failed_action(action, "No pack card at position " .. action.positions[1])
            send_state()
            return
        end
        -- If there are additional positions, they are hand cards to highlight
        if #action.positions > 1 then
            selection_positions = {}
            for i=2, #action.positions do
                table.insert(selection_positions, action.positions[i])
            end
            select_cards(selection_positions)
        end
        -- Check if the pack card can be selected after highlighting the cards
        if G.STATE == G.STATES.STANDARD_PACK then
            -- Can select any standard pack card
        elseif not can_select_card(pack_card) then
            add_failed_action(action, "Cannot select this pack card. Please try a different selection.")
            send_state()
            return
        end
        -- Highlight and use the pack card
        pack_card:highlight(true)
        G.FUNCS.use_card({config = {ref_table = pack_card}})
    elseif action.action == "round_select" then
        G.FUNCS.toggle_shop()
    elseif action.action == "play_round" then
        for blind, state in pairs(G.GAME.round_resets.blind_states) do
            if state == "Select" then
                G.FUNCS.select_blind({
                    config = {
                        ref_table = G.P_BLINDS[G.GAME.round_resets.blind_choices[blind]]
                    }
                }) 
                break
            end
        end
    elseif action.action == "skip_booster" then
        G.FUNCS.skip_booster()
    elseif action.action == "skip_round" then
        for blind, state in pairs(G.GAME.round_resets.blind_states) do
            if state == "Select" then
                G.FUNCS.skip_blind(G.blind_select:get_UIE_by_ID(blind))
                break  -- Ensure only 1 skip.
            end
        end
    elseif action.action == "rearrange_hand" then
        local new_cards = {}
        for _, pos in ipairs(action.positions) do
            table.insert(new_cards, G.hand.cards[pos])
        end
        G.hand.cards = new_cards
    elseif action.action == "rearrange_jokers" then
        local new_cards = {}
        for _, pos in ipairs(action.positions) do
            table.insert(new_cards, G.jokers.cards[pos])
        end
        G.jokers.cards = new_cards
    elseif action.action == "use_consumable" then
        card = G.consumeables.cards[action.positions[1]]
        if not card then
            add_failed_action(action, "No consumable at position " .. action.positions[1])
            send_state()
            return
        end
        -- If there are additional positions, they are hand cards to highlight
        if #action.positions > 1 then
            -- Unhighlight all cards first
            G.hand:unhighlight_all()
            -- Reorder cards so that the selected cards are first in the hand in the order selected
            local new_hand_idx_order = {}
            for i=2, #action.positions do
                hand_idx = action.positions[i]
                table.insert(new_hand_idx_order, hand_idx)
            end
            for i=1, #G.hand.cards do
                if not has_value(new_hand_idx_order, i) then
                    table.insert(new_hand_idx_order, i)
                end
            end
            local new_hand_cards = {}
            for i=1, #new_hand_idx_order do
                table.insert(new_hand_cards, G.hand.cards[new_hand_idx_order[i]])
            end
            G.hand.cards = new_hand_cards
            -- Highlight the specified hand cards (positions 2 onwards are hand card indices)
            for i = 1, #action.positions - 1 do
                if G.hand.cards[i] and not G.hand.cards[i].highlighted then
                    G.hand:add_to_highlighted(G.hand.cards[i])
                end
            end
        end
        -- Check if the consumable can be used after highlighting the cards
        can_use = card:can_use_consumeable()
        if not can_use then
            add_failed_action(action, "Cannot use consumable at position " .. action.positions[1])
            send_state()
            return
        end
        -- Highlight and use the pack card
        card:highlight(true)
        G.FUNCS.use_card({config = {ref_table = card}})
    elseif action.action == "buy_and_use_consumable" then
        -- Buy a consumable from the shop and immediately use it (doesn't take up consumable slot)
        card = G.shop_jokers.cards[action.positions[1]]
        if not card then
            add_failed_action(action, "No card at shop position " .. action.positions[1])
            send_state()
            return
        end
        if not card.ability.consumeable then
            add_failed_action(action, "Card at position " .. action.positions[1] .. " is not a consumable")
            send_state()
            return
        end
        if not card.children.buy_and_use_button then
            add_failed_action(action, "Card at position " .. action.positions[1] .. " does not have buy_and_use option")
            send_state()
            return
        end
        if not can_buy(card) then
            add_failed_action(action, "Cannot afford consumable at position " .. action.positions[1])
            send_state()
            return
        end
        if not card:can_use_consumeable() then
            add_failed_action(action, "Cannot use consumable at position " .. action.positions[1])
            send_state()
            return
        end
        -- Trigger buy_and_use via the button definition (has id='buy_and_use' which tells buy_from_shop to use immediately)
        G.FUNCS.buy_from_shop(card.children.buy_and_use_button.definition)
    elseif action.action == "sell_joker" then
        local joker = G.jokers.cards[action.positions[1]]
        if joker then
            if joker:can_sell_card() then
                joker:sell_card()
            else
                add_failed_action(action, "Cannot sell joker at position " .. action.positions[1])
                send_state()
                return
            end
        else
            print("No joker at position " .. action.positions[1])
            G.bot_failed_action = action
            send_state()
            return
        end
    elseif action.action == "sell_consumable" then
        local consumable = G.consumeables.cards[action.positions[1]]
        if consumable then
            -- Consumables area has type 'joker', so can_sell_card should work for consumables too
            -- But let's check if the card can actually be sold
            if consumable:can_sell_card() then
                consumable:sell_card()
            elseif consumable.sell_cost and consumable.sell_cost > 0 then
                -- If it has a sell cost but can_sell_card returns false, try to sell directly
                -- (may fail if game state doesn't allow it)
                consumable:sell_card()
            else
                add_failed_action(action, "Cannot sell consumable at position " .. action.positions[1])
                send_state()
                return
            end
        else
            add_failed_action(action, "No consumable at position " .. action.positions[1])
            send_state()
            return
        end
    elseif action.action == "reroll_shop" then
        if ((G.GAME.dollars-G.GAME.bankrupt_at) - G.GAME.current_round.reroll_cost < 0) and G.GAME.current_round.reroll_cost ~= 0 then
            add_failed_action(action, "Cannot reroll shop. You do not have enough dollars to reroll.")
            send_state()
            return
        else
            G.FUNCS.reroll_shop()
        end
    end
    -- Reset failed action if action completed successfully
    G.bot_failed_action = nil
end