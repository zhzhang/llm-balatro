import { db, gameRuns } from 'astro:db';
import Database from 'better-sqlite3';

// https://astro.build/db/seed
// Only migrate gameRuns table (fast) - skip screenshots and turn_history (slow)
export default async function seed() {
  // Open the SQLite database
  const sqliteDb = new Database('game_history.db', { readonly: true });

  // Migrate game_runs table only
  const runsData = sqliteDb.prepare('SELECT * FROM game_runs').all() as any[];
  for (const row of runsData) {
    await db.insert(gameRuns).values({
      id: row.id,
      runId: row.run_id,
      startedAt: row.started_at,
      gamePlan: row.game_plan,
      reflection: row.reflection,
      bestHand: row.best_hand,
      finalAnte: row.final_ante,
      finalRound: row.final_round,
      endedAt: row.ended_at,
      seed: row.seed,
      agent: row.agent,
      completed: row.completed,
      won: row.won,
    });
  }

  sqliteDb.close();
}
