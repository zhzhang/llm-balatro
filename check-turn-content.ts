import { Database } from 'bun:sqlite';

const db = new Database('game_history.db', { readonly: true });

// Get a runId
const run = db.query(`
  SELECT run_id FROM game_runs 
  WHERE agent = 'gemini' AND seed = '422J6NUH' 
  LIMIT 1
`).get() as { run_id: string };

console.log('Run ID:', run.run_id);

// Get turn 1 data
const turn1Data = db.query(`
  SELECT type, blob
  FROM turn_history 
  WHERE run_id = ? AND turn = 1
  ORDER BY type
`).all(run.run_id) as Array<{ type: string; blob: string }>;

console.log('\n=== Turn 1 Data ===\n');

for (const item of turn1Data) {
  console.log(`\n--- ${item.type.toUpperCase()} ---`);
  console.log(item.blob.substring(0, 500));
  console.log('...\n');
}

db.close();
