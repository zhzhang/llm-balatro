"""SQLite database module for storing game history."""

import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import StrEnum

DB_PATH = Path(__file__).parent / "game_history.db"


class EntryType(StrEnum):
    GAME_STATE = "game_state"
    AGENT_REPLY = "agent_reply"


SAVE_FILE_PATH = Path.home() / ".local/share/love/balatro-fork/1/save.jkr"


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    # Create turn_history table (renamed from history)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS turn_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            turn INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('game_state', 'agent_reply')),
            blob TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            ante INTEGER,
            sent_to_game INTEGER DEFAULT 0,
            hand_result TEXT,
            UNIQUE(run_id, turn, type)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_turn_history_run_id ON turn_history(run_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_turn_history_run_turn ON turn_history(run_id, turn)
    """)

    # Create game_runs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT UNIQUE NOT NULL,
            started_at TEXT NOT NULL,
            game_plan TEXT,
            reflection TEXT,
            best_hand INTEGER,
            final_ante INTEGER,
            final_round INTEGER,
            ended_at TEXT,
            seed TEXT,
            agent TEXT,
            completed INTEGER DEFAULT 0,
            won INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_game_runs_run_id ON game_runs(run_id)
    """)

    # Create save_snapshots table for storing save file blobs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS save_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            turn INTEGER NOT NULL,
            save_data BLOB NOT NULL,
            timestamp TEXT NOT NULL,
            UNIQUE(run_id, turn)
        )
    """)

    # Create current_run table to store the current run ID (single row)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS current_run (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            run_id TEXT,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_save_snapshots_run_turn ON save_snapshots(run_id, turn)
    """)

    # Create screenshots table for storing game screenshots
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS screenshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            turn INTEGER NOT NULL,
            screenshot_data BLOB NOT NULL,
            timestamp TEXT NOT NULL,
            UNIQUE(run_id, turn)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_screenshots_run_turn ON screenshots(run_id, turn)
    """)

    # Create game_object_notes table for storing analysis notes
    # (renamed from item_notes to include boss blinds)
    # Version column added to track note iterations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_object_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('joker', 'consumable', 'voucher', 'tag', 'boss_blind')),
            notes TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            UNIQUE(name, type, version)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_game_object_notes_name ON game_object_notes(name)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_game_object_notes_type ON game_object_notes(type)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_game_object_notes_name_type ON game_object_notes(name, type)
    """)

    conn.commit()
    conn.close()


def migrate_game_object_notes_to_versioned():
    """Migrate existing game_object_notes table to add version column.

    This function handles the migration of existing databases that don't have
    the version column yet. It recreates the table with the version column
    and migrates existing data as version 1.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Check if version column exists
    cursor.execute("PRAGMA table_info(game_object_notes)")
    columns = [row[1] for row in cursor.fetchall()]

    if "version" in columns:
        print("game_object_notes table already has version column, skipping migration")
        conn.close()
        return

    print("Migrating game_object_notes table to add version column...")

    # Create new table with version column
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_object_notes_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('joker', 'consumable', 'voucher', 'tag', 'boss_blind')),
            notes TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            UNIQUE(name, type, version)
        )
    """)

    # Copy existing data with version=1
    cursor.execute("""
        INSERT INTO game_object_notes_new (name, type, notes, version, updated_at)
        SELECT name, type, notes, 1, updated_at
        FROM game_object_notes
    """)

    # Drop old table and rename new one
    cursor.execute("DROP TABLE game_object_notes")
    cursor.execute("ALTER TABLE game_object_notes_new RENAME TO game_object_notes")

    # Recreate indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_game_object_notes_name ON game_object_notes(name)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_game_object_notes_type ON game_object_notes(type)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_game_object_notes_name_type ON game_object_notes(name, type)
    """)

    conn.commit()
    conn.close()
    print("Migration complete!")


def migrate_game_runs_add_seed():
    """Migrate existing game_runs table to add seed column.

    This function handles the migration of existing databases that don't have
    the seed column yet. It uses ALTER TABLE to add the column.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Check if seed column exists
    cursor.execute("PRAGMA table_info(game_runs)")
    columns = [row[1] for row in cursor.fetchall()]

    if "seed" in columns:
        conn.close()
        return

    print("Migrating game_runs table to add seed column...")

    # Add seed column
    cursor.execute("""
        ALTER TABLE game_runs ADD COLUMN seed TEXT
    """)

    conn.commit()
    conn.close()
    print("Migration complete! Added seed column to game_runs table.")


def migrate_game_runs_add_agent():
    """Migrate existing game_runs table to add agent column.

    This function handles the migration of existing databases that don't have
    the agent column yet. It uses ALTER TABLE to add the column.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Check if agent column exists
    cursor.execute("PRAGMA table_info(game_runs)")
    columns = [row[1] for row in cursor.fetchall()]

    if "agent" in columns:
        conn.close()
        return

    print("Migrating game_runs table to add agent column...")

    # Add agent column
    cursor.execute("""
        ALTER TABLE game_runs ADD COLUMN agent TEXT
    """)

    conn.commit()
    conn.close()
    print("Migration complete! Added agent column to game_runs table.")


def migrate_game_runs_add_completion_status():
    """Migrate existing game_runs table to add completed and won columns.

    This function handles the migration of existing databases that don't have
    the completed and won columns yet. It uses ALTER TABLE to add the columns.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Check if columns exist
    cursor.execute("PRAGMA table_info(game_runs)")
    columns = [row[1] for row in cursor.fetchall()]

    if "completed" not in columns:
        print("Migrating game_runs table to add completed column...")
        cursor.execute("""
            ALTER TABLE game_runs ADD COLUMN completed INTEGER DEFAULT 0
        """)

    if "won" not in columns:
        print("Migrating game_runs table to add won column...")
        cursor.execute("""
            ALTER TABLE game_runs ADD COLUMN won INTEGER DEFAULT 0
        """)

    cursor.execute("""
        UPDATE game_runs 
        SET completed = 1
    """)

    conn.commit()
    print("Migration complete! Added completed and won columns to game_runs table.")

    conn.close()


def generate_run_id() -> str:
    """Generate a new unique run ID."""
    return str(uuid.uuid4())[:8]


def create_game_run(run_id: str, agent: str) -> int:
    """Create a new game run entry."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO game_runs (run_id, started_at, agent)
        VALUES (?, ?, ?)
    """,
        (run_id, datetime.now().isoformat(), agent),
    )

    entry_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return entry_id


def save_game_plan(run_id: str, plan_text: str) -> None:
    """Save the game plan for a run."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE game_runs SET game_plan = ? WHERE run_id = ?
    """,
        (plan_text, run_id),
    )

    conn.commit()
    conn.close()


def get_game_plan(run_id: str) -> Optional[str]:
    """Get the game plan for a specific run."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT game_plan FROM game_runs WHERE run_id = ?
    """,
        (run_id,),
    )

    row = cursor.fetchone()
    conn.close()

    return row["game_plan"] if row else None


def get_run_seed(run_id: str) -> Optional[str]:
    """Get the seed for a specific run."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT seed FROM game_runs WHERE run_id = ?
    """,
        (run_id,),
    )

    row = cursor.fetchone()
    conn.close()

    return row["seed"] if row else None


def get_run_agent(run_id: str) -> Optional[str]:
    """Get the agent for a specific run."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT agent FROM game_runs WHERE run_id = ?
    """,
        (run_id,),
    )

    row = cursor.fetchone()
    conn.close()

    return row["agent"] if row else None


def set_run_seed(run_id: str, seed: str) -> None:
    """Set the seed for a specific run."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE game_runs SET seed = ? WHERE run_id = ?
    """,
        (seed, run_id),
    )

    conn.commit()
    conn.close()


def get_latest_run_id() -> Optional[str]:
    """Get the most recent run_id."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT run_id FROM turn_history 
        ORDER BY id DESC 
        LIMIT 1
    """)

    row = cursor.fetchone()
    conn.close()

    return row["run_id"] if row else None


def get_next_turn(run_id: str) -> int:
    """Get the next turn number for a run."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT MAX(turn) as max_turn FROM turn_history 
        WHERE run_id = ?
    """,
        (run_id,),
    )

    row = cursor.fetchone()
    conn.close()

    max_turn = row["max_turn"] if row and row["max_turn"] is not None else -1
    return max_turn + 1


# Path where Love2D saves the screenshot (same directory as the save file)
SCREENSHOT_PATH = Path.home() / ".local/share/love/balatro-fork/bot_screenshot.png"


def read_game_screenshot() -> Optional[bytes]:
    """Read the screenshot captured by the Love2D game."""
    try:
        if SCREENSHOT_PATH.exists():
            return SCREENSHOT_PATH.read_bytes()
        else:
            print(f"Screenshot not found at {SCREENSHOT_PATH}")
            return None
    except Exception as e:
        print(f"Error reading screenshot: {e}")
        return None


async def save_state(
    run_id: str,
    turn: int,
    data: Dict[str, Any],
    ante: Optional[int] = None,
) -> int:
    """Save a game state entry and its save file snapshot to the database.

    Also broadcasts the game state to WebSocket clients if agent_messages is provided.
    """
    conn = get_connection()
    cursor = conn.cursor()

    timestamp = datetime.now().isoformat()

    cursor.execute(
        """
        INSERT INTO turn_history (run_id, turn, type, blob, timestamp, ante)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (run_id, turn, EntryType.GAME_STATE.value, json.dumps(data), timestamp, ante),
    )

    entry_id = cursor.lastrowid

    # Always save snapshot with game state
    if SAVE_FILE_PATH.exists():
        try:
            save_data = SAVE_FILE_PATH.read_bytes()
            cursor.execute(
                """
                INSERT OR REPLACE INTO save_snapshots (run_id, turn, save_data, timestamp)
                VALUES (?, ?, ?, ?)
            """,
                (run_id, turn, save_data, timestamp),
            )
            print(f"Saved snapshot for run {run_id}, turn {turn}")
        except Exception as e:
            print(f"Error saving snapshot: {e}")
    else:
        print(f"Save file not found at {SAVE_FILE_PATH}")

    conn.commit()
    conn.close()

    screenshot_bytes = read_game_screenshot()
    if screenshot_bytes:
        save_screenshot(run_id, turn, screenshot_bytes)

    # Broadcast game state immediately (before agent responds)
    # This await ensures the WebSocket message is sent BEFORE we start the API call
    # Import server locally to avoid circular dependency
    import server

    state_entry = {
        "type": "game_state",
        "run_id": run_id,
        "turn": turn,
        "timestamp": timestamp,
        "game_state": data.get("game_state"),
        "state_string": data.get("state_string"),
        "prompt": data.get("prompt"),
    }
    await server.broadcast_to_clients(state_entry)

    return entry_id


def save_agent_reply(
    run_id: str, turn: int, data: Dict[str, Any], sent_to_game: bool = False
) -> int:
    """Save an agent reply entry to the database.

    Args:
        run_id: The run ID.
        turn: The turn number.
        data: The agent reply data.
        sent_to_game: Whether this action has been sent to the game yet.
                      Defaults to False for async processing model.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO turn_history (run_id, turn, type, blob, timestamp, sent_to_game)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            run_id,
            turn,
            EntryType.AGENT_REPLY.value,
            json.dumps(data),
            datetime.now().isoformat(),
            1 if sent_to_game else 0,
        ),
    )

    entry_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return entry_id


def get_turn_state(run_id: str, turn: int) -> Optional[Dict[str, Any]]:
    """Get the game state data for a specific turn.

    Returns the parsed game_state blob data, or None if not found.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT blob FROM turn_history
        WHERE run_id = ? AND turn = ? AND type = 'game_state'
    """,
        (run_id, turn),
    )

    row = cursor.fetchone()
    conn.close()

    if row:
        return json.loads(row["blob"])
    return None


def update_hand_result(run_id: str, turn: int, hand_result: Dict[str, Any]) -> bool:
    """Update the hand_result column for a specific turn's game_state entry.

    Args:
        run_id: The run ID.
        turn: The turn number.
        hand_result: Dictionary with 'hand_type' and 'chips_earned' keys.

    Returns:
        True if the update was successful, False otherwise.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE turn_history
        SET hand_result = ?
        WHERE run_id = ? AND turn = ? AND type = 'game_state'
    """,
        (json.dumps(hand_result), run_id, turn),
    )

    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return updated


def get_pending_action(run_id: str) -> Optional[Dict[str, Any]]:
    """Get the latest agent_reply that hasn't been sent to the game yet.

    Returns the action data with turn number, or None if no pending action.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT turn, blob FROM turn_history
        WHERE run_id = ? AND type = 'agent_reply' AND sent_to_game = 0
        ORDER BY turn DESC
        LIMIT 1
    """,
        (run_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if row:
        data = json.loads(row["blob"])
        data["turn"] = row["turn"]
        return data
    return None


def mark_action_sent(run_id: str, turn: int) -> bool:
    """Mark an agent_reply as sent to the game.

    Returns True if an action was marked, False otherwise.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE turn_history
        SET sent_to_game = 1
        WHERE run_id = ? AND turn = ? AND type = 'agent_reply'
    """,
        (run_id, turn),
    )

    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return updated


def get_run_history(run_id: str) -> List[Dict[str, Any]]:
    """Get all entries for a specific run."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, run_id, turn, type, blob, timestamp, ante, hand_result 
        FROM turn_history 
        WHERE run_id = ?
        ORDER BY turn, type
    """,
        (run_id,),
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row["id"],
            "run_id": row["run_id"],
            "turn": row["turn"],
            "type": row["type"],
            "data": json.loads(row["blob"]),
            "timestamp": row["timestamp"],
            "ante": row["ante"],
            "hand_result": json.loads(row["hand_result"])
            if row["hand_result"]
            else None,
        }
        for row in rows
    ]


def get_run_history_by_ante(run_id: str) -> Dict[int, List[Dict[str, Any]]]:
    """Get all entries for a specific run, grouped by ante.

    Returns a dictionary where keys are ante numbers and values are lists of entries.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, run_id, turn, type, blob, timestamp, ante 
        FROM turn_history 
        WHERE run_id = ?
        ORDER BY ante, turn, type
    """,
        (run_id,),
    )

    rows = cursor.fetchall()
    conn.close()

    # Group by ante
    result: Dict[int, List[Dict[str, Any]]] = {}
    for row in rows:
        ante = row["ante"] if row["ante"] is not None else 0
        if ante not in result:
            result[ante] = []
        result[ante].append(
            {
                "id": row["id"],
                "run_id": row["run_id"],
                "turn": row["turn"],
                "type": row["type"],
                "data": json.loads(row["blob"]),
                "timestamp": row["timestamp"],
                "ante": ante,
            }
        )

    return result


def get_all_runs() -> List[Dict[str, Any]]:
    """Get summary of all runs."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            th.run_id,
            MIN(th.timestamp) as started_at,
            MAX(th.timestamp) as last_activity,
            MAX(th.turn) as total_turns,
            gr.seed,
            gr.agent,
            gr.completed,
            gr.won
        FROM turn_history th
        LEFT JOIN game_runs gr ON th.run_id = gr.run_id
        GROUP BY th.run_id
        ORDER BY MAX(th.id) DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "run_id": row["run_id"],
            "started_at": row["started_at"],
            "last_activity": row["last_activity"],
            "total_turns": row["total_turns"] + 1,
            "seed": row["seed"],
            "agent": row["agent"],
            "completed": bool(row["completed"])
            if row["completed"] is not None
            else False,
            "won": bool(row["won"]) if row["won"] is not None else False,
        }
        for row in rows
    ]


def get_full_history() -> List[Dict[str, Any]]:
    """Get all history entries, grouped by turn with game_state and agent_reply paired."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, run_id, turn, type, blob, timestamp 
        FROM turn_history 
        ORDER BY id DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row["id"],
            "run_id": row["run_id"],
            "turn": row["turn"],
            "type": row["type"],
            "data": json.loads(row["blob"]),
            "timestamp": row["timestamp"],
        }
        for row in rows
    ]


def get_combined_history() -> List[Dict[str, Any]]:
    """Get history with game_state and agent_reply combined per turn for frontend display."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            gs.run_id,
            gs.turn,
            gs.blob as game_state_blob,
            gs.timestamp as game_state_timestamp,
            ar.blob as agent_reply_blob,
            ar.timestamp as agent_reply_timestamp
        FROM turn_history gs
        LEFT JOIN turn_history ar ON gs.run_id = ar.run_id AND gs.turn = ar.turn AND ar.type = 'agent_reply'
        WHERE gs.type = 'game_state'
        ORDER BY gs.id DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        game_state_data = json.loads(row["game_state_blob"])
        agent_reply_data = (
            json.loads(row["agent_reply_blob"]) if row["agent_reply_blob"] else {}
        )

        # Combine into format expected by frontend
        combined = {
            "run_id": row["run_id"],
            "turn": row["turn"],
            "timestamp": row["agent_reply_timestamp"] or row["game_state_timestamp"],
            "game_state": game_state_data.get("game_state"),
            "state_string": game_state_data.get("state_string"),
            "prompt": game_state_data.get("prompt"),
            "action": agent_reply_data.get("action"),
            "positions": agent_reply_data.get("positions"),
            "reasoning": agent_reply_data.get("reasoning"),
        }
        result.append(combined)

    return result


def clear_run(run_id: str) -> int:
    """Clear all entries for a specific run and all associated records.

    This deletes:
    - turn_history entries (game states and agent replies)
    - game_runs entry
    - save_snapshots
    - screenshots

    Returns the number of turn_history entries deleted.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Delete turn history entries
    cursor.execute("DELETE FROM turn_history WHERE run_id = ?", (run_id,))
    deleted = cursor.rowcount

    # Delete game_runs entry
    cursor.execute("DELETE FROM game_runs WHERE run_id = ?", (run_id,))

    # Delete save snapshots
    cursor.execute("DELETE FROM save_snapshots WHERE run_id = ?", (run_id,))
    snapshots_deleted = cursor.rowcount

    # Delete screenshots
    cursor.execute("DELETE FROM screenshots WHERE run_id = ?", (run_id,))
    screenshots_deleted = cursor.rowcount

    conn.commit()
    conn.close()

    print(
        f"Deleted run {run_id}: {deleted} turn entries, {snapshots_deleted} snapshots, {screenshots_deleted} screenshots"
    )
    return deleted


def save_reflection(
    run_id: str,
    reflection_text: str,
    best_hand: Optional[int] = None,
    final_ante: Optional[int] = None,
    final_round: Optional[int] = None,
) -> None:
    """Save a game reflection to the game_runs table.

    Sets completed=1 to indicate the run has reached an end state.
    If won is not already set to 1 (by mark_run_as_won), sets it to 0 (indicating a loss).
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Update the reflection and mark as completed
    # If won is not already 1, set it to 0 (indicating a loss)
    cursor.execute(
        """
        UPDATE game_runs 
        SET reflection = ?, best_hand = ?, final_ante = ?, final_round = ?, 
            ended_at = ?, completed = 1, won = CASE WHEN won = 1 THEN 1 ELSE 0 END
        WHERE run_id = ?
    """,
        (
            reflection_text,
            best_hand,
            final_ante,
            final_round,
            datetime.now().isoformat(),
            run_id,
        ),
    )

    conn.commit()
    conn.close()


def set_win_status(
    run_id: str,
    won: bool,
) -> None:
    """Set the win status for a run."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE game_runs 
        SET won = ?, completed = 1
        WHERE run_id = ?
    """,
        (won, run_id),
    )

    conn.commit()
    conn.close()


def get_reflection_for_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Get the reflection for a specific run."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT reflection, best_hand, final_ante, final_round FROM game_runs 
        WHERE run_id = ?
    """,
        (run_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if row and row["reflection"]:
        return {
            "reflection": row["reflection"],
            "best_hand": row["best_hand"],
            "final_ante": row["final_ante"],
            "final_round": row["final_round"],
        }
    return None


def get_all_reflections() -> List[Dict[str, Any]]:
    """Get all reflections with their run IDs and timestamps."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT run_id, reflection, best_hand, final_ante, final_round, started_at, ended_at 
        FROM game_runs 
        WHERE reflection IS NOT NULL
        ORDER BY id DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "run_id": row["run_id"],
            "reflection": row["reflection"],
            "best_hand": row["best_hand"],
            "final_ante": row["final_ante"],
            "final_round": row["final_round"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
        }
        for row in rows
    ]


def save_game_object_note(name: str, object_type: str, notes: str) -> None:
    """Save a new version of a game object note in the database.

    Each time this is called, it creates a new version entry with an incremented
    version number. The agent will always read the latest version.

    Args:
        name: The name of the game object.
        object_type: One of 'joker', 'consumable', 'voucher', 'tag', or 'boss_blind'.
        notes: The analysis notes for this game object.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get the current max version for this name/type
    cursor.execute(
        """
        SELECT MAX(version) as max_version FROM game_object_notes 
        WHERE name = ? AND type = ?
    """,
        (name, object_type),
    )

    row = cursor.fetchone()
    next_version = (
        (row["max_version"] + 1) if (row and row["max_version"] is not None) else 1
    )

    # Insert new version
    cursor.execute(
        """
        INSERT INTO game_object_notes (name, type, notes, version, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """,
        (
            name,
            object_type,
            notes,
            next_version,
            datetime.now().isoformat(),
        ),
    )

    conn.commit()
    conn.close()


# Backward compatibility alias
def save_item_note(name: str, item_type: str, notes: str) -> None:
    """Deprecated: Use save_game_object_note instead."""
    save_game_object_note(name, item_type, notes)


def get_game_object_note(name: str, object_type: str) -> Optional[str]:
    """Get the latest version of notes for a specific game object.

    This function always returns the most recent version of the notes.
    The agent will always read this latest version.

    Args:
        name: The name of the game object.
        object_type: One of 'joker', 'consumable', 'voucher', 'tag', or 'boss_blind'.

    Returns:
        The latest notes for the game object, or None if not found.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT notes FROM game_object_notes 
        WHERE name = ? AND type = ?
        ORDER BY version DESC
        LIMIT 1
    """,
        (name, object_type),
    )

    row = cursor.fetchone()
    conn.close()

    return row["notes"] if row else None


# Backward compatibility alias
def get_item_note(name: str, item_type: str) -> Optional[str]:
    """Deprecated: Use get_game_object_note instead."""
    return get_game_object_note(name, item_type)


def get_all_game_object_notes() -> List[Dict[str, Any]]:
    """Get all game object notes from the database (latest versions only).

    Returns only the most recent version of each game object's notes.

    Returns:
        List of dictionaries with name, type, notes, version, and updated_at.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, type, notes, version, updated_at 
        FROM game_object_notes g1
        WHERE version = (
            SELECT MAX(version) 
            FROM game_object_notes g2 
            WHERE g2.name = g1.name AND g2.type = g1.type
        )
        ORDER BY type, name
    """)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "name": row["name"],
            "type": row["type"],
            "notes": row["notes"],
            "version": row["version"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


# Backward compatibility alias
def get_all_item_notes() -> List[Dict[str, Any]]:
    """Deprecated: Use get_all_game_object_notes instead."""
    return get_all_game_object_notes()


def get_game_object_note_history(name: str, object_type: str) -> List[Dict[str, Any]]:
    """Get all versions of notes for a specific game object.

    Returns all versions in descending order (latest first).

    Args:
        name: The name of the game object.
        object_type: One of 'joker', 'consumable', 'voucher', 'tag', or 'boss_blind'.

    Returns:
        List of dictionaries with notes, version, and updated_at for each version.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT notes, version, updated_at 
        FROM game_object_notes 
        WHERE name = ? AND type = ?
        ORDER BY version DESC
    """,
        (name, object_type),
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "notes": row["notes"],
            "version": row["version"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def get_game_object_note_version(
    name: str, object_type: str, version: int
) -> Optional[str]:
    """Get a specific version of notes for a game object.

    Args:
        name: The name of the game object.
        object_type: One of 'joker', 'consumable', 'voucher', 'tag', or 'boss_blind'.
        version: The version number to retrieve.

    Returns:
        The notes for the specified version, or None if not found.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT notes FROM game_object_notes 
        WHERE name = ? AND type = ? AND version = ?
    """,
        (name, object_type, version),
    )

    row = cursor.fetchone()
    conn.close()

    return row["notes"] if row else None


def is_run_finished(run_id: str) -> bool:
    """Check if a run is finished (has a reflection saved)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT reflection FROM game_runs WHERE run_id = ?",
        (run_id,),
    )

    row = cursor.fetchone()
    conn.close()

    return row is not None and row["reflection"] is not None


def clear_run_reflection(run_id: str) -> bool:
    """Clear the reflection and end-of-game data for a run.

    This allows a finished run to be resumed by clearing:
    - reflection
    - best_hand
    - final_ante
    - final_round
    - ended_at
    - completed
    - won

    Returns True if a reflection was cleared, False otherwise.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE game_runs 
        SET reflection = NULL, best_hand = NULL, final_ante = NULL, 
            final_round = NULL, ended_at = NULL, completed = 0, won = 0
        WHERE run_id = ? AND reflection IS NOT NULL
    """,
        (run_id,),
    )

    cleared = cursor.rowcount > 0
    conn.commit()
    conn.close()

    if cleared:
        print(f"Cleared reflection and end-of-game data for run {run_id}")
    return cleared


def get_all_game_runs_with_outcomes() -> List[Dict[str, Any]]:
    """Get all game runs with reflections and outcome stats for plan generation."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT run_id, started_at, game_plan, reflection, best_hand, final_ante, final_round, ended_at, completed, won
        FROM game_runs 
        WHERE reflection IS NOT NULL
        ORDER BY id ASC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "run_id": row["run_id"],
            "started_at": row["started_at"],
            "game_plan": row["game_plan"],
            "reflection": row["reflection"],
            "best_hand": row["best_hand"],
            "final_ante": row["final_ante"],
            "final_round": row["final_round"],
            "ended_at": row["ended_at"],
            "completed": bool(row["completed"])
            if row["completed"] is not None
            else False,
            "won": bool(row["won"]) if row["won"] is not None else False,
        }
        for row in rows
    ]


def save_snapshot(run_id: str, turn: int) -> bool:
    """Save a snapshot of the current save file to the database."""
    if not SAVE_FILE_PATH.exists():
        print(f"Save file not found at {SAVE_FILE_PATH}")
        return False

    try:
        save_data = SAVE_FILE_PATH.read_bytes()
    except Exception as e:
        print(f"Error reading save file: {e}")
        return False

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT OR REPLACE INTO save_snapshots (run_id, turn, save_data, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            (run_id, turn, save_data, datetime.now().isoformat()),
        )
        conn.commit()
        print(f"Saved snapshot for run {run_id}, turn {turn}")
        return True
    except Exception as e:
        print(f"Error saving snapshot: {e}")
        return False
    finally:
        conn.close()


def get_snapshot(run_id: str, turn: int) -> Optional[bytes]:
    """Get a save file snapshot from the database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT save_data FROM save_snapshots
        WHERE run_id = ? AND turn = ?
    """,
        (run_id, turn),
    )

    row = cursor.fetchone()
    conn.close()

    return row["save_data"] if row else None


def restore_snapshot(run_id: str, turn: int) -> bool:
    """Restore a save file snapshot to the save file path."""
    save_data = get_snapshot(run_id, turn)

    if save_data is None:
        print(f"No snapshot found for run {run_id}, turn {turn}")
        return False

    try:
        # Ensure the directory exists
        SAVE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SAVE_FILE_PATH.write_bytes(save_data)
        print(f"Restored snapshot for run {run_id}, turn {turn} to {SAVE_FILE_PATH}")
        return True
    except Exception as e:
        print(f"Error restoring snapshot: {e}")
        return False


def get_snapshots_for_run(run_id: str) -> List[Dict[str, Any]]:
    """Get all snapshots for a specific run."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, run_id, turn, timestamp, LENGTH(save_data) as size
        FROM save_snapshots
        WHERE run_id = ?
        ORDER BY turn DESC
    """,
        (run_id,),
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row["id"],
            "run_id": row["run_id"],
            "turn": row["turn"],
            "timestamp": row["timestamp"],
            "size": row["size"],
        }
        for row in rows
    ]


def get_current_run_id_from_db() -> Optional[str]:
    """Get the current run ID from the database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT run_id FROM current_run WHERE id = 1")
    row = cursor.fetchone()
    conn.close()

    return row["run_id"] if row else None


def set_current_run_id_in_db(run_id: str) -> None:
    """Set the current run ID in the database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO current_run (id, run_id, updated_at)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET run_id = ?, updated_at = ?
    """,
        (run_id, datetime.now().isoformat(), run_id, datetime.now().isoformat()),
    )

    conn.commit()
    conn.close()


def delete_turn_data_from_turn(run_id: str, from_turn: int) -> int:
    """Delete all turn history entries for a run starting from a specific turn.

    This deletes both game_state and agent_reply entries.
    Returns the number of deleted entries.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM turn_history 
        WHERE run_id = ? AND turn >= ?
    """,
        (run_id, from_turn),
    )

    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    print(f"Deleted {deleted} entries from run {run_id} starting from turn {from_turn}")
    return deleted


def delete_snapshots_from_turn(run_id: str, from_turn: int) -> int:
    """Delete all save snapshots for a run starting from a specific turn.

    Returns the number of deleted snapshots.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM save_snapshots 
        WHERE run_id = ? AND turn >= ?
    """,
        (run_id, from_turn),
    )

    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    print(
        f"Deleted {deleted} snapshots from run {run_id} starting from turn {from_turn}"
    )
    return deleted


def save_screenshot(run_id: str, turn: int, screenshot_data: bytes) -> bool:
    """Save a screenshot to the database."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT OR REPLACE INTO screenshots (run_id, turn, screenshot_data, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            (run_id, turn, screenshot_data, datetime.now().isoformat()),
        )
        conn.commit()
        print(f"Saved screenshot for run {run_id}, turn {turn}")
        return True
    except Exception as e:
        print(f"Error saving screenshot: {e}")
        return False
    finally:
        conn.close()


def get_screenshot(run_id: str, turn: int) -> Optional[bytes]:
    """Get a screenshot from the database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT screenshot_data FROM screenshots
        WHERE run_id = ? AND turn = ?
    """,
        (run_id, turn),
    )

    row = cursor.fetchone()
    conn.close()

    return row["screenshot_data"] if row else None


def get_screenshots_for_run(run_id: str) -> List[Dict[str, Any]]:
    """Get all screenshots for a specific run (metadata only, not the image data)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, run_id, turn, timestamp, LENGTH(screenshot_data) as size
        FROM screenshots
        WHERE run_id = ?
        ORDER BY turn DESC
    """,
        (run_id,),
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row["id"],
            "run_id": row["run_id"],
            "turn": row["turn"],
            "timestamp": row["timestamp"],
            "size": row["size"],
        }
        for row in rows
    ]


def delete_screenshots_from_turn(run_id: str, from_turn: int) -> int:
    """Delete all screenshots for a run starting from a specific turn.

    Returns the number of deleted screenshots.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM screenshots 
        WHERE run_id = ? AND turn >= ?
    """,
        (run_id, from_turn),
    )

    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    print(
        f"Deleted {deleted} screenshots from run {run_id} starting from turn {from_turn}"
    )
    return deleted


def get_next_seed_for_agent(source_agent: str, target_agent: str) -> Optional[str]:
    """Find the next seed where source_agent has run but target_agent hasn't finished.

    Args:
        source_agent: The agent that should have seeds (e.g., "gemini")
        target_agent: The agent to check for completion (e.g., "claude")

    Returns:
        The next seed that needs to be run by target_agent, or None if all seeds are done.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get all distinct seeds where source_agent has run
    cursor.execute(
        """
        SELECT DISTINCT seed
        FROM game_runs
        WHERE agent = ? AND seed IS NOT NULL
        ORDER BY started_at ASC
    """,
        (source_agent,),
    )

    source_seeds = [row["seed"] for row in cursor.fetchall()]

    # For each seed, check if target_agent has a finished run (has reflection)
    print(source_seeds)
    for seed in source_seeds:
        cursor.execute(
            """
            SELECT run_id, completed
            FROM game_runs
            WHERE agent = ? AND seed = ?
        """,
            (target_agent, seed),
        )

        target_run = cursor.fetchone()

        # If no run exists or the run is not finished (no completed), this is the next seed
        if target_run is None or not target_run["completed"]:
            conn.close()
            return seed

    conn.close()
    return None


def cleanup_orphaned_run_data() -> Dict[str, int]:
    """Delete all records keyed on run_id where the run_id no longer exists in game_runs.

    Also deletes game_runs entries that have no associated records in other tables.

    This migration cleans up:
    - Orphaned turn_history (game states and agent replies)
    - Orphaned save_snapshots
    - Orphaned screenshots
    - Invalid current_run references
    - Empty game_runs (runs with no history, snapshots, or screenshots)

    Returns:
        A dictionary with counts of deleted records from each table.
    """
    conn = get_connection()
    cursor = conn.cursor()

    deleted_counts = {
        "turn_history": 0,
        "save_snapshots": 0,
        "screenshots": 0,
        "current_run": 0,
        "game_runs": 0,
    }

    print("Starting cleanup of orphaned run_id data...")

    # Delete orphaned turn_history entries
    cursor.execute("""
        DELETE FROM turn_history
        WHERE run_id NOT IN (SELECT run_id FROM game_runs)
    """)
    deleted_counts["turn_history"] = cursor.rowcount

    # Delete orphaned save_snapshots
    cursor.execute("""
        DELETE FROM save_snapshots
        WHERE run_id NOT IN (SELECT run_id FROM game_runs)
    """)
    deleted_counts["save_snapshots"] = cursor.rowcount

    # Delete orphaned screenshots
    cursor.execute("""
        DELETE FROM screenshots
        WHERE run_id NOT IN (SELECT run_id FROM game_runs)
    """)
    deleted_counts["screenshots"] = cursor.rowcount

    # Clear current_run if it references a non-existent run_id
    cursor.execute("""
        UPDATE current_run
        SET run_id = NULL
        WHERE run_id NOT IN (SELECT run_id FROM game_runs)
    """)
    deleted_counts["current_run"] = cursor.rowcount

    # Delete game_runs that have no associated records in any other table
    cursor.execute("""
        DELETE FROM game_runs
        WHERE run_id NOT IN (SELECT DISTINCT run_id FROM turn_history)
        AND run_id NOT IN (SELECT DISTINCT run_id FROM save_snapshots)
        AND run_id NOT IN (SELECT DISTINCT run_id FROM screenshots)
    """)
    deleted_counts["game_runs"] = cursor.rowcount

    conn.commit()
    conn.close()

    print("Cleanup complete!")
    print(f"  Deleted {deleted_counts['turn_history']} orphaned turn_history entries")
    print(f"  Deleted {deleted_counts['save_snapshots']} orphaned save_snapshots")
    print(f"  Deleted {deleted_counts['screenshots']} orphaned screenshots")
    print(f"  Cleared {deleted_counts['current_run']} invalid current_run references")
    print(f"  Deleted {deleted_counts['game_runs']} empty game_runs")

    return deleted_counts


# Initialize database on module import
init_db()
migrate_game_object_notes_to_versioned()
migrate_game_runs_add_seed()
migrate_game_runs_add_agent()
migrate_game_runs_add_completion_status()
cleanup_orphaned_run_data()
