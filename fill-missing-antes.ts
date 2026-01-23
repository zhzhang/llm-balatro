import { Database } from 'bun:sqlite';

const dbPath = process.argv[2] || 'game_history.db';

try {
  const db = new Database(dbPath);

  console.log(`\n=== Filling missing final_ante values in ${dbPath} ===\n`);

  // Find all game runs where final_ante is NULL
  const runsWithMissingAnte = db.query(`
    SELECT run_id as runId, id
    FROM game_runs 
    WHERE final_ante IS NULL
  `).all() as { runId: string; id: number }[];

  console.log(`Found ${runsWithMissingAnte.length} game run(s) with missing final_ante\n`);

  if (runsWithMissingAnte.length === 0) {
    console.log('✅ No missing final_ante values to fill!');
    db.close();
    process.exit(0);
  }

  let updatedCount = 0;

  // For each run, find the maximum ante from turn history
  for (const run of runsWithMissingAnte) {
    const maxAnteResult = db.query(`
      SELECT MAX(ante) as maxAnte
      FROM turn_history
      WHERE run_id = ? AND ante IS NOT NULL
    `).get(run.runId) as { maxAnte: number | null };

    if (maxAnteResult.maxAnte !== null) {
      // Update the game run with the max ante found
      db.query(`
        UPDATE game_runs
        SET final_ante = ?
        WHERE run_id = ?
      `).run(maxAnteResult.maxAnte, run.runId);

      console.log(`✅ Updated run ${run.runId}: final_ante = ${maxAnteResult.maxAnte}`);
      updatedCount++;
    } else {
      console.log(`⚠️  No ante found in turn history for run ${run.runId}`);
    }
  }

  console.log(`\n=== Summary ===`);
  console.log(`Updated ${updatedCount} of ${runsWithMissingAnte.length} run(s)`);

  db.close();
} catch (error) {
  console.error('Error filling missing antes:', error);
  process.exit(1);
}
