#!/usr/bin/env python

"""Balatro Bot Server with WebSocket support and game process management."""

import asyncio
import json
import os
import sys
import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response

from bot_action import process_state_async
from db import (
    clear_run,
    clear_run_reflection,
    create_game_run,
    delete_screenshots_from_turn,
    delete_snapshots_from_turn,
    delete_turn_data_from_turn,
    generate_run_id,
    get_all_game_runs_with_outcomes,
    get_all_game_object_notes,
    get_game_object_note,
    get_game_object_note_history,
    get_game_object_note_version,
    get_all_item_notes,
    get_item_note,
    get_all_runs,
    get_combined_history,
    get_current_run_id_from_db,
    get_next_seed_for_agent,
    get_pending_action,
    get_reflection_for_run,
    get_run_history,
    get_run_seed,
    get_screenshot,
    get_screenshots_for_run,
    get_snapshots_for_run,
    init_db,
    is_run_finished,
    mark_action_sent,
    set_win_status,
    restore_snapshot,
    set_current_run_id_in_db,
    set_run_seed,
)
from game_definitions import (
    JOKERS,
    VOUCHERS,
    TAROT_CARDS,
    SPECTRAL_CARDS,
    SEALS,
    ENHANCEMENTS,
    EDITIONS,
    BOSS_BLINDS,
    get_all_consumables,
)


# WebSocket clients
websocket_clients = set()


AGENT = "openai"


# Game process management
game_process = None
output_tasks = []


async def broadcast_to_clients(data):
    """Broadcast data to all connected WebSocket clients (async version)"""
    if not websocket_clients:
        return

    message = json.dumps(data)

    disconnected = set()
    for client in websocket_clients:
        try:
            await client.send_text(message)
        except Exception as e:
            print(f"Error sending to client: {e}")
            disconnected.add(client)
    # Remove disconnected clients
    websocket_clients.difference_update(disconnected)


def load_card_reference_data() -> str:
    """Load and format card reference data from JSON files for the game plan prompt."""
    reference_text = "\n# BALATRO CARD REFERENCE\n"

    # Jokers
    reference_text += "\n## JOKERS\n"
    reference_text += "Format: Name (Rarity, $Cost) - Effect\n\n"
    for joker in JOKERS:
        reference_text += f"- {joker['name']} ({joker['rarity']}, ${joker['cost']}) - {joker['effect']}\n"

    # Vouchers
    voucher_names = {v["key"]: v["name"] for v in VOUCHERS}
    reference_text += "\n## VOUCHERS\n"
    reference_text += (
        "Format: Name - Effect [Requires: prerequisite redeemed voucher if any]\n\n"
    )
    for voucher in VOUCHERS:
        req_key = voucher.get("requires")
        req = f" [Requires: {voucher_names.get(req_key, req_key)}]" if req_key else ""
        reference_text += f"- {voucher['name']} - {voucher['effect']}{req}\n"

    # Tarot Cards
    reference_text += "\n## TAROT CARDS\n"
    for tarot in TAROT_CARDS:
        reference_text += f"- {tarot['name']} - {tarot['effect']}\n"

    # Spectral Cards
    reference_text += "\n## SPECTRAL CARDS\n"
    for spectral in SPECTRAL_CARDS:
        reference_text += f"- {spectral['name']} - {spectral['effect']}\n"

    reference_text += "\n## PLANET CARDS\n"
    reference_text += (
        "Planet cards upgrade the types of played poker hands by 1 level.\n\n"
    )

    reference_text += "\n## Card Modifiers\n"
    reference_text += "Seals, enhancements, and editions are bonus effects that may be applied to cards or joker cards. Each card can only have one of each type of modifier applied to it."

    # Seals
    reference_text += "\n## SEALS\n"
    for seal in SEALS:
        reference_text += f"- {seal['name']} - {seal['effect']}\n"

    # Enhancements
    reference_text += "\n## ENHANCEMENTS (for playing cards)\n"
    for enhancement in ENHANCEMENTS:
        reference_text += f"- {enhancement['name']} - {enhancement['effect']}\n"

    # Editions
    reference_text += "\n## EDITIONS (for playing cards and jokers)\n"
    for edition in EDITIONS:
        reference_text += f"- {edition['name']} - {edition['effect']}\n"

    # Boss Blinds
    reference_text += "\n## BOSS BLINDS\n"
    reference_text += "Boss blinds appear at the end of each Ante. Showdown bosses only appear at Ante 8.\n"
    for blind in BOSS_BLINDS:
        showdown = " (Showdown)" if blind.get("showdown") else ""
        reference_text += f"- {blind['name']}{showdown} - {blind['effect']} (x{blind['chip_multiplier']} chips)\n"

    # Ante base chips
    reference_text += "\n## ANTE BASE CHIPS\n"
    reference_text += "The base chips for each ante are:\n"
    reference_text += "Ante 1: 300\n"
    reference_text += "Ante 2: 800\n"
    reference_text += "Ante 3: 2000\n"
    reference_text += "Ante 4: 5000\n"
    reference_text += "Ante 5: 11000\n"
    reference_text += "Ante 6: 20000\n"
    reference_text += "Ante 7: 35000\n"
    reference_text += "Ante 8: 50000\n"
    reference_text += "For each ante, Small Blind requires the base chips, Big Blind requires 1.5x the base chips, and Boss Blinds multiply the base chips by their own specific chip multiplier, shown above."

    return reference_text


async def start_new_run() -> str:
    """Start a new run, create game_runs entry, and generate game plan.

    Looks for seeds where 'gemini' has run but 'claude' hasn't finished.
    If no such seed exists, exits the thread.
    """
    # Find the next seed where gemini has run but claude hasn't finished
    next_seed = get_next_seed_for_agent("gemini", AGENT)

    if next_seed is None:
        print(
            f"No seeds available for {AGENT} to run. All Gemini seeds have been completed by {AGENT}."
        )
        print("Exiting thread...")
        sys.exit(0)

    print(f"Found seed for {AGENT} to run: {next_seed}")

    run_id = generate_run_id()

    # Create the game_runs entry with the manual strategy flag and agent
    create_game_run(run_id, AGENT)

    # Set the seed for this run
    set_run_seed(run_id, next_seed)
    print(f"Set seed '{next_seed}' for run {run_id}")

    # # Generate game plan from past reflections (async)
    # print("Generating new game plan for run ", run_id)
    # await generate_game_plan(run_id)

    # Save to database as current run
    set_current_run_id_in_db(run_id)

    return run_id


def get_current_run_id() -> str:
    """Get the current run ID from DB, creating a new one if needed."""
    run_id = get_current_run_id_from_db()
    if run_id is None:
        run_id = generate_run_id()
        set_current_run_id_in_db(run_id)
    return run_id


def continue_run(run_id: str, from_turn: int) -> str:
    """Continue a previous run from a specific turn.

    This sets the run ID as current and deletes all turn data from the specified turn onwards.
    If the run was finished (has a reflection), the reflection and end-of-game summaries
    are also cleared to allow resuming the run.
    The save snapshot should be restored before calling this function.
    """
    # Set as current run in DB
    set_current_run_id_in_db(run_id)

    # Clear reflection if this is a finished run being resumed
    clear_run_reflection(run_id)

    # Delete turn data from this turn onwards (both game_state and agent_reply)
    delete_turn_data_from_turn(run_id, from_turn)

    # Delete snapshots from this turn onwards
    delete_snapshots_from_turn(run_id, from_turn)

    # Delete screenshots from this turn onwards
    delete_screenshots_from_turn(run_id, from_turn)

    print(f"Continuing run {run_id} from turn {from_turn}")
    return run_id


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    # Startup
    print("Server starting up...")

    # Check if database exists, create it if not
    from pathlib import Path

    db_path = Path(__file__).parent / "game_history.db"
    if not db_path.exists():
        print(f"Database not found at {db_path}. Creating new database...")
        init_db()
        print("Database created successfully.")
    else:
        print(f"Database found at {db_path}")
        # Still call init_db to ensure schema is up to date
        init_db()
        print("Database schema verified.")

    yield
    # Shutdown
    print("Server shutting down...")
    await cleanup_game_process_async()


app = FastAPI(lifespan=lifespan)

# Track background tasks for agent processing
agent_tasks: dict = {}


@app.post("/state")
async def receive_state(request: Request):
    """Endpoint for the game to send state. Kicks off async agent processing."""
    state = await request.json()
    run_id = get_current_run_id()

    # Check and store seed for this run
    if "seed" in state:
        current_seed = state["seed"]
        stored_seed = get_run_seed(run_id)

        if stored_seed is None:
            # First time receiving state for this run, store the seed
            set_run_seed(run_id, current_seed)
            print(f"Stored seed '{current_seed}' for run {run_id}")
        elif stored_seed != current_seed:
            # Seed mismatch - this should not happen
            error_msg = (
                f"ERROR: Seed mismatch for run {run_id}! "
                f"Expected '{stored_seed}' but got '{current_seed}'"
            )
            print(error_msg)
            return {"status": "error", "message": error_msg}, 400

    # Kick off async task to process state and generate action
    async def log_exceptions(task):
        try:
            await task
        except Exception as e:
            import traceback

            print(f"Error processing state: {e}")
            traceback.print_exc()

    task = asyncio.create_task(log_exceptions(process_state_async(state)))
    agent_tasks[run_id] = task

    return {"status": "received", "run_id": run_id}


@app.get("/action")
async def get_action():
    """Endpoint for the game to poll for a pending action.

    Returns the latest action that hasn't been sent to the game yet,
    and marks it as sent.
    """
    run_id = get_current_run_id()
    pending = get_pending_action(run_id)

    if pending:
        turn = pending.pop("turn")
        mark_action_sent(run_id, turn)
        return {
            "status": "ready",
            "action": pending.get("action"),
            "positions": pending.get("positions", []),
        }
    else:
        return {"status": "pending"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time state updates"""
    await websocket.accept()
    websocket_clients.add(websocket)

    # Send the full history to the newly connected client
    history = get_combined_history()
    await websocket.send_text(json.dumps({"type": "history", "data": history}))

    try:
        # Keep the connection alive and listen for messages
        while True:
            data = await websocket.receive_text()
            # Handle any client messages if needed
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        websocket_clients.remove(websocket)


@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serve the web monitor interface"""
    templates_dir = Path(__file__).parent / "templates"
    index_file = templates_dir / "index.html"

    if index_file.exists():
        return index_file.read_text()
    else:
        return "<h1>Error: Template not found</h1>"


@app.get("/api/history")
async def get_history():
    """REST endpoint for getting full history (fallback)"""
    return get_combined_history()


@app.get("/api/runs")
async def get_runs():
    """REST endpoint for getting list of all runs"""
    return get_all_runs()


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    """REST endpoint for getting history for a specific run"""
    return get_run_history(run_id)


@app.get("/api/latest")
async def get_latest():
    """REST endpoint for getting latest state (fallback)"""
    history = get_combined_history()
    if history:
        return history[0]  # Combined history is ordered DESC
    return {"error": "No history available"}


@app.get("/api/current-run")
async def current_run():
    """Get the current run ID"""
    return {"run_id": get_current_run_id()}


@app.delete("/api/runs/{run_id}")
async def delete_run(run_id: str):
    """Clear history for a specific run"""
    deleted = clear_run(run_id)
    return {"deleted": deleted}


@app.get("/api/reflections")
async def get_reflections():
    """Get all game runs with reflections and outcomes"""
    return get_all_game_runs_with_outcomes()


@app.get("/api/runs/{run_id}/reflection")
async def get_run_reflection(run_id: str):
    """Get the reflection for a specific run"""
    reflection = get_reflection_for_run(run_id)
    if reflection:
        return {"run_id": run_id, "reflection": reflection}
    return {"run_id": run_id, "reflection": None}


@app.get("/api/runs/{run_id}/snapshots")
async def get_run_snapshots(run_id: str):
    """Get all save file snapshots for a specific run"""
    return get_snapshots_for_run(run_id)


@app.get("/api/runs/{run_id}/finished")
async def check_run_finished(run_id: str):
    """Check if a run is finished (has a reflection saved)"""
    finished = is_run_finished(run_id)
    return {"run_id": run_id, "finished": finished}


@app.post("/api/runs/{run_id}/snapshots/{turn}/restore")
async def restore_run_snapshot(run_id: str, turn: int):
    """Restore a save file snapshot to the game save location"""
    success = restore_snapshot(run_id, turn)
    if success:
        return {"status": "restored", "run_id": run_id, "turn": turn}
    return {
        "status": "error",
        "message": f"Failed to restore snapshot for run {run_id}, turn {turn}",
    }


@app.get("/api/runs/{run_id}/screenshots")
async def get_run_screenshots(run_id: str):
    """Get all screenshot metadata for a specific run"""
    return get_screenshots_for_run(run_id)


@app.get("/api/runs/{run_id}/screenshots/{turn}")
async def get_run_screenshot(run_id: str, turn: int):
    """Get a specific screenshot image for a run and turn"""
    screenshot_data = get_screenshot(run_id, turn)
    if screenshot_data:
        return Response(content=screenshot_data, media_type="image/png")
    return {"error": f"Screenshot not found for run {run_id}, turn {turn}"}


@app.post("/api/runs/{run_id}/continue/{turn}")
async def continue_run_from_turn(run_id: str, turn: int):
    """Continue a run from a specific turn.

    This will:
    1. Restore the save snapshot for that turn
    2. Set the run ID as the current run in the database
    3. Delete all turn data (game_state and agent_reply) for that turn and beyond
    4. Delete all snapshots for that turn and beyond
    """
    # First restore the snapshot
    success = restore_snapshot(run_id, turn)
    if not success:
        return {
            "status": "error",
            "message": f"Failed to restore snapshot for run {run_id}, turn {turn}",
        }

    # Continue the run (sets current run ID and deletes future turn data)
    continue_run(run_id, turn)

    return {
        "status": "continued",
        "run_id": run_id,
        "from_turn": turn,
        "message": f"Continuing run {run_id} from turn {turn}. Start the game to continue playing.",
    }


# ============================================================================
# Item Notes API
# ============================================================================


@app.get("/api/game-object-notes")
async def get_game_object_notes():
    """Get all game object notes from the database"""
    return get_all_game_object_notes()


@app.get("/api/game-object-notes/{object_type}")
async def get_game_object_notes_by_type(object_type: str):
    """Get all game object notes of a specific type (joker, consumable, voucher, tag, boss_blind)"""
    all_notes = get_all_game_object_notes()
    return [note for note in all_notes if note["type"] == object_type]


@app.get("/api/game-object-notes/{object_type}/{name}")
async def get_game_object_note_endpoint(object_type: str, name: str):
    """Get the latest version of notes for a specific game object"""
    notes = get_game_object_note(name, object_type)
    if notes:
        return {"name": name, "type": object_type, "notes": notes}
    return {"name": name, "type": object_type, "notes": None}


@app.get("/api/game-object-notes/{object_type}/{name}/history")
async def get_game_object_note_history_endpoint(object_type: str, name: str):
    """Get all versions of notes for a specific game object"""
    history = get_game_object_note_history(name, object_type)
    return {"name": name, "type": object_type, "history": history}


@app.get("/api/game-object-notes/{object_type}/{name}/version/{version}")
async def get_game_object_note_version_endpoint(
    object_type: str, name: str, version: int
):
    """Get a specific version of notes for a game object"""
    notes = get_game_object_note_version(name, object_type, version)
    if notes:
        return {"name": name, "type": object_type, "version": version, "notes": notes}
    return {"name": name, "type": object_type, "version": version, "notes": None}


# Backward compatibility endpoints
@app.get("/api/item-notes")
async def get_item_notes():
    """Deprecated: Use /api/game-object-notes instead"""
    return get_all_item_notes()


@app.get("/api/item-notes/{item_type}")
async def get_item_notes_by_type(item_type: str):
    """Deprecated: Use /api/game-object-notes/{object_type} instead"""
    all_notes = get_all_item_notes()
    return [note for note in all_notes if note["type"] == item_type]


@app.get("/api/item-notes/{item_type}/{name}")
async def get_item_note_endpoint(item_type: str, name: str):
    """Deprecated: Use /api/game-object-notes/{object_type}/{name} instead"""
    notes = get_item_note(name, item_type)
    if notes:
        return {"name": name, "type": item_type, "notes": notes}
    return {"name": name, "type": item_type, "notes": None}


# ============================================================================
# Reference Data API (for the notes browser)
# ============================================================================


@app.get("/api/reference/jokers")
async def get_reference_jokers():
    """Get all jokers from the reference data"""
    return JOKERS


@app.get("/api/reference/vouchers")
async def get_reference_vouchers():
    """Get all vouchers from the reference data"""
    return VOUCHERS


@app.get("/api/reference/consumables")
async def get_reference_consumables():
    """Get all consumables (tarot + spectral cards) from the reference data"""
    return get_all_consumables()


@app.get("/api/reference/boss-blinds")
async def get_reference_boss_blinds():
    """Get all boss blinds from the reference data"""
    return BOSS_BLINDS


@app.get("/history", response_class=HTMLResponse)
async def get_history_page():
    """Serve the game history page"""
    templates_dir = Path(__file__).parent / "templates"
    history_file = templates_dir / "history.html"

    if history_file.exists():
        return HTMLResponse(content=history_file.read_text())
    return HTMLResponse(content="<h1>History page not found</h1>", status_code=404)


@app.get("/notes", response_class=HTMLResponse)
async def get_notes_page():
    """Serve the game object notes browser page"""
    templates_dir = Path(__file__).parent / "templates"
    notes_file = templates_dir / "notes.html"

    if notes_file.exists():
        return notes_file.read_text()
    else:
        return "<h1>Error: Template not found</h1>"


async def forward_output(stream, prefix):
    """Forward output from a stream to console with a prefix"""
    while True:
        line = await stream.readline()
        if not line:
            break
        try:
            decoded = line.decode("utf-8").rstrip()
            print(f"[{prefix}] {decoded}")
        except UnicodeDecodeError:
            print(f"[{prefix}] <binary data>")


@app.post("/game/start")
async def start_game(run_id: str = None, turn: int = None):
    """Start the game process, killing any existing one first.

    If run_id and turn are provided, continues an existing run from that turn.
    Otherwise, starts a new run.
    """
    global game_process, output_tasks

    # Kill existing game process if running
    if game_process and game_process.returncode is None:
        try:
            game_process.terminate()
            try:
                await asyncio.wait_for(game_process.wait(), timeout=5.0)
                print("Previous game process stopped gracefully")
            except asyncio.TimeoutError:
                game_process.kill()
                await game_process.wait()
                print("Previous game process killed")
        except Exception as e:
            print(f"Error stopping previous game: {e}")

    try:
        # Cancel any existing output tasks
        for task in output_tasks:
            task.cancel()
        output_tasks.clear()

        # Determine if we're continuing a run or starting a new one
        is_continuing = run_id is not None and turn is not None
        env = os.environ.copy()

        if is_continuing:
            # Restore the snapshot and set up continuation
            success = restore_snapshot(run_id, turn)
            if not success:
                return {
                    "status": "error",
                    "message": f"Failed to restore snapshot for run {run_id}, turn {turn}",
                }

            # Continue the run (sets current run ID and deletes future turn data)
            continue_run(run_id, turn)
            print(f"Continuing run {run_id} from turn {turn}")

            # Set CONTINUE env var for the game
            env["CONTINUE"] = "true"
        else:
            # Start a new run
            run_id = await start_new_run()
            print(f"Started new run with ID: {run_id}")

            # Check if there's a seed for this run and pass it to the game
            seed = get_run_seed(run_id)
            if seed:
                env["SEED"] = seed
                print(f"Starting game with seed: {seed}")
            print(seed)

        # Start the game process with asyncio
        game_process = await asyncio.create_subprocess_exec(
            "love",
            ".",
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # Create tasks to forward stdout and stderr
        stdout_task = asyncio.create_task(
            forward_output(game_process.stdout, "GAME-OUT")
        )
        stderr_task = asyncio.create_task(
            forward_output(game_process.stderr, "GAME-ERR")
        )
        output_tasks.extend([stdout_task, stderr_task])

        print(f"Game started with PID: {game_process.pid}")
        result = {"status": "started", "pid": game_process.pid, "run_id": run_id}
        if is_continuing:
            result["continued_from_turn"] = turn
        return result
    except Exception as e:
        print(f"Error starting game: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/game/stop")
async def stop_game():
    """Stop the game process"""
    global game_process, output_tasks

    if game_process and game_process.returncode is None:
        try:
            # Terminate the process
            game_process.terminate()

            # Wait for it to stop
            try:
                await asyncio.wait_for(game_process.wait(), timeout=5.0)
                status = "stopped"
            except asyncio.TimeoutError:
                # Force kill if it doesn't stop gracefully
                game_process.kill()
                await game_process.wait()
                status = "killed"

            # Cancel output tasks
            for task in output_tasks:
                task.cancel()
            output_tasks.clear()

            print(f"Game process stopped: {status}")
            return {"status": status}
        except Exception as e:
            print(f"Error stopping game: {e}")
            return {"status": "error", "message": str(e)}

    return {"status": "not_running"}


@app.post("/game/win")
async def record_win(request: Request):
    """Endpoint to receive notification that the game was won.

    Called from Lua when win_game() is triggered.
    Records the win in the database for the current run and starts a new game.
    """
    try:
        win_data = await request.json()
        run_id = get_current_run_id()

        if not run_id:
            return {"status": "error", "message": "No active run"}

        final_ante = win_data.get("ante", 0)
        final_round = win_data.get("round", 0)

        # Mark the run as won in the database
        set_win_status(run_id, True)

        print(
            f"✓ Game won! Run {run_id} completed at ante {final_ante}, round {final_round}"
        )
        print("Starting new game automatically...")

        # Start a new game automatically
        start_result = await start_game(run_id=None, turn=None)

        return {
            "status": "success",
            "message": f"Win recorded for run {run_id}, new game started",
            "run_id": run_id,
            "final_ante": final_ante,
            "final_round": final_round,
            "new_game": start_result,
        }
    except Exception as e:
        print(f"Error recording win: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/game/status")
async def game_status():
    """Get the status of the game process"""
    global game_process

    if game_process is None:
        return {"status": "not_started"}
    elif game_process.returncode is None:
        return {"status": "running", "pid": game_process.pid}
    else:
        return {"status": "stopped", "exit_code": game_process.returncode}


async def cleanup_game_process_async():
    """Async cleanup function to stop the game process on server shutdown"""
    global game_process, output_tasks

    # Cancel output tasks
    for task in output_tasks:
        if not task.done():
            task.cancel()

    if game_process and game_process.returncode is None:
        print("Stopping game process...")
        game_process.terminate()
        try:
            await asyncio.wait_for(game_process.wait(), timeout=5.0)
            print("Game process stopped gracefully")
        except asyncio.TimeoutError:
            print("Game process didn't stop, killing it...")
            game_process.kill()
            await game_process.wait()
            print("Game process killed")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7777))
    host = os.environ.get("HOST", "0.0.0.0")

    print("=" * 60)
    print("Balatro Bot Server")
    print("=" * 60)
    print(f"Web Monitor: http://localhost:{port}")
    print(f"Bot API: http://localhost:{port} (POST)")
    print(f"WebSocket: ws://localhost:{port}/ws")
    print("=" * 60)
    print("\nEnvironment variables:")
    print("  MANUAL_STRATEGY=1  - Use manual strategy prompt for new runs")
    print("  PORT=7777          - Server port")
    print("  HOST=0.0.0.0       - Server host")
    print("\nPress Ctrl+C to stop the server")
    print()

    try:
        uvicorn.run(app, host=host, port=port)
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
