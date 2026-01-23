import { Database } from 'bun:sqlite';

// Sync the updated final_ante values from game_history.db to Astro DB
const sourceDb = new Database('game_history.db', { readonly: true });
const targetDb = new Database('.astro/content.db');

console.log('\n=== Syncing final_ante values to Astro DB ===\n');

try {
  // Get all runs with their final_ante from source
  const sourceRuns = sourceDb.query(`
    SELECT run_id, final_ante
    FROM game_runs
    WHERE final_ante IS NOT NULL
  `).all() as { run_id: string; final_ante: number }[];

  console.log(`Found ${sourceRuns.length} runs with final_ante in source DB\n`);

  // Update each run in the target DB
  const updateStmt = targetDb.prepare(`
    UPDATE gameRuns
    SET finalAnte = ?
    WHERE runId = ?
  `);

  let updatedCount = 0;
  
  targetDb.run('BEGIN TRANSACTION');
  
  for (const run of sourceRuns) {
    const result = updateStmt.run(run.final_ante, run.run_id);
    if (result.changes > 0) {
      console.log(`✅ Updated run ${run.run_id}: finalAnte = ${run.final_ante}`);
      updatedCount++;
    }
  }
  
  targetDb.run('COMMIT');

  console.log(`\n=== Summary ===`);
  console.log(`Updated ${updatedCount} run(s) in Astro DB`);

  // Verify
  const missingCount = targetDb.query('SELECT COUNT(*) as count FROM gameRuns WHERE finalAnte IS NULL').get() as { count: number };
  console.log(`Runs still missing finalAnte in Astro DB: ${missingCount.count}`);

} catch (error) {
  targetDb.run('ROLLBACK');
  console.error('Error syncing data:', error);
  throw error;
} finally {
  sourceDb.close();
  targetDb.close();
}
