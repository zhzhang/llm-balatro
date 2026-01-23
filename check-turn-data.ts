import { Database } from 'bun:sqlite';

const db = new Database('game_history.db', { readonly: true });

// Get a runId
const run = db.query(`
  SELECT run_id FROM game_runs 
  WHERE agent = 'gemini' AND seed = '422J6NUH' 
  LIMIT 1
`).get() as { run_id: string };

console.log('Run ID:', run.run_id);

// Check turn_history for this run
const history = db.query(`
  SELECT turn, type, LENGTH(blob) as blob_length
  FROM turn_history 
  WHERE run_id = ? 
  ORDER BY turn, type
  LIMIT 20
`).all(run.run_id);

console.log('\nTurn history (first 20):');
console.table(history);

// Check total count by type
const counts = db.query(`
  SELECT type, COUNT(*) as count
  FROM turn_history 
  WHERE run_id = ?
  GROUP BY type
`).all(run.run_id);

console.log('\nCounts by type:');
console.table(counts);

db.close();
