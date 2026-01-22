import { Database } from 'bun:sqlite';

// This script migrates data from game_history.db to Astro DB format
// Run with: bun run migrate-to-astro-db-fast.ts

const sqliteDb = new Database('game_history.db', { readonly: true });
const astroDB = new Database('.astro/content.db');

console.log('Starting migration from game_history.db to Astro DB...');

// Use a transaction for better performance
astroDB.run('BEGIN TRANSACTION');

try {
  // Migrate game_runs table
  console.log('\nMigrating game_runs...');
  const runsData = sqliteDb.query('SELECT * FROM game_runs').all() as any[];
  const insertRun = astroDB.prepare(`
    INSERT INTO gameRuns (id, runId, startedAt, gamePlan, reflection, bestHand, finalAnte, finalRound, endedAt, seed, agent, completed, won)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  for (const row of runsData) {
    insertRun.run(
      row.id,
      row.run_id,
      row.started_at,
      row.game_plan,
      row.reflection,
      row.best_hand,
      row.final_ante,
      row.final_round,
      row.ended_at,
      row.seed,
      row.agent,
      row.completed,
      row.won
    );
  }
  console.log(`  ✓ Migrated ${runsData.length} rows`);

  // Migrate screenshots table (converting BLOB to base64)
  console.log('\nMigrating screenshots...');
  const screenshotsData = sqliteDb.query('SELECT * FROM screenshots').all() as any[];
  const insertScreenshot = astroDB.prepare(`
    INSERT INTO screenshots (id, runId, turn, screenshotData, timestamp)
    VALUES (?, ?, ?, ?, ?)
  `);

  for (const row of screenshotsData) {
    const screenshotBase64 = Buffer.from(row.screenshot_data).toString('base64');
    insertScreenshot.run(
      row.id,
      row.run_id,
      row.turn,
      screenshotBase64,
      row.timestamp
    );
  }
  console.log(`  ✓ Migrated ${screenshotsData.length} rows`);

  // Migrate turn_history table
  console.log('\nMigrating turn_history...');
  const turnHistoryData = sqliteDb.query('SELECT * FROM turn_history').all() as any[];
  const insertTurn = astroDB.prepare(`
    INSERT INTO turnHistory (id, runId, turn, type, blob, timestamp, ante, sentToGame, handResult)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  for (const row of turnHistoryData) {
    insertTurn.run(
      row.id,
      row.run_id,
      row.turn,
      row.type,
      row.blob,
      row.timestamp,
      row.ante,
      row.sent_to_game,
      row.hand_result
    );
  }
  console.log(`  ✓ Migrated ${turnHistoryData.length} rows`);

  astroDB.run('COMMIT');
  console.log('\n✅ Migration complete!');
} catch (error) {
  astroDB.run('ROLLBACK');
  console.error('❌ Migration failed:', error);
  throw error;
} finally {
  sqliteDb.close();
  astroDB.close();
}
