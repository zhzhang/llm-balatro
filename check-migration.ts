import { Database } from 'bun:sqlite';

const astroDB = new Database('.astro/content.db', { readonly: true });

console.log('\nChecking Astro DB migration status:\n');

const gameRunsCount = astroDB.query('SELECT COUNT(*) as count FROM gameRuns').get() as { count: number };
console.log(`gameRuns: ${gameRunsCount.count} rows`);

const screenshotsCount = astroDB.query('SELECT COUNT(*) as count FROM screenshots').get() as { count: number };
console.log(`screenshots: ${screenshotsCount.count} rows`);

const turnHistoryCount = astroDB.query('SELECT COUNT(*) as count FROM turnHistory').get() as { count: number };
console.log(`turnHistory: ${turnHistoryCount.count} rows`);

astroDB.close();

const sqliteDb = new Database('game_history.db', { readonly: true });

console.log('\nOriginal SQLite DB:\n');

const origGameRunsCount = sqliteDb.query('SELECT COUNT(*) as count FROM game_runs').get() as { count: number };
console.log(`game_runs: ${origGameRunsCount.count} rows`);

const origScreenshotsCount = sqliteDb.query('SELECT COUNT(*) as count FROM screenshots').get() as { count: number };
console.log(`screenshots: ${origScreenshotsCount.count} rows`);

const origTurnHistoryCount = sqliteDb.query('SELECT COUNT(*) as count FROM turn_history').get() as { count: number };
console.log(`turn_history: ${origTurnHistoryCount.count} rows`);

sqliteDb.close();
