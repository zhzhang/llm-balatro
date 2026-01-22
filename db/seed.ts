import { db, gameRuns, screenshots, turnHistory } from 'astro:db';
import { Database } from 'bun:sqlite';

// https://astro.build/db/seed
export default async function seed() {
  // Open the SQLite database
  const sqliteDb = new Database('game_history.db', { readonly: true });

  console.log('Starting migration from game_history.db...');

  // Migrate game_runs table
  console.log('Migrating game_runs...');
  const runsData = sqliteDb.query('SELECT * FROM game_runs').all() as any[];
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
  console.log(`  ✓ Migrated ${runsData.length} rows`);

  // Migrate screenshots table (converting BLOB to base64)
  console.log('Migrating screenshots...');
  const screenshotsData = sqliteDb.query('SELECT * FROM screenshots').all() as any[];
  for (const row of screenshotsData) {
    const screenshotBase64 = Buffer.from(row.screenshot_data).toString('base64');
    await db.insert(screenshots).values({
      id: row.id,
      runId: row.run_id,
      turn: row.turn,
      screenshotData: screenshotBase64,
      timestamp: row.timestamp,
    });
  }
  console.log(`  ✓ Migrated ${screenshotsData.length} rows`);

  // Migrate turn_history table
  console.log('Migrating turn_history...');
  const turnHistoryData = sqliteDb.query('SELECT * FROM turn_history').all() as any[];
  for (const row of turnHistoryData) {
    await db.insert(turnHistory).values({
      id: row.id,
      runId: row.run_id,
      turn: row.turn,
      type: row.type,
      blob: row.blob,
      timestamp: row.timestamp,
      ante: row.ante,
      sentToGame: row.sent_to_game,
      handResult: row.hand_result,
    });
  }
  console.log(`  ✓ Migrated ${turnHistoryData.length} rows`);

  sqliteDb.close();
  console.log('Migration complete!');
}
