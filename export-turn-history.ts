import { db, gameRuns } from 'astro:db';
import { mkdir, writeFile } from 'fs/promises';
import { join } from 'path';
import Database from 'better-sqlite3';

/**
 * Export all turn history data from database to static JSON and image files
 * Organized as: public/turn-history/{agent}/{seed}/{turn}.json and {turn}.png
 */

interface TurnData {
	turn: number;
	ante?: number;
	state?: string;
	action?: string;
	reasoning?: string;
	hasScreenshot: boolean;
}

interface RunMetadata {
	agent: string;
	seed: string;
	runId: string;
	outcome: string;
	turns: number[];
}

export default async function exportTurnHistory() {
	console.log('Starting turn history export...');

	// Get all game runs from Astro DB
	const runs = await db.select().from(gameRuns).all();
	console.log(`Found ${runs.length} game runs`);

	// Open SQLite database for turn history and screenshots
	const sqliteDb = new Database('game_history.db', { readonly: true });

	const runMetadataList: RunMetadata[] = [];

	for (const run of runs) {
		if (!run.agent || !run.seed) {
			console.log(`Skipping run ${run.runId} - missing agent or seed`);
			continue;
		}

		console.log(`Processing ${run.agent}/${run.seed}...`);

		// Create directory structure
		const baseDir = join(process.cwd(), 'public', 'turn-history', run.agent, run.seed);
		await mkdir(baseDir, { recursive: true });

		// Get all turn history for this run from SQLite
		const history = sqliteDb
			.prepare('SELECT * FROM turn_history WHERE run_id = ?')
			.all(run.runId) as any[];

		// Get all screenshots for this run from SQLite
		const screenShots = sqliteDb
			.prepare('SELECT * FROM screenshots WHERE run_id = ?')
			.all(run.runId) as any[];

		// Organize data by turn
		const turnMap = new Map<number, TurnData>();

		// Process turn history
		for (const item of history) {
			if (!turnMap.has(item.turn)) {
				turnMap.set(item.turn, {
					turn: item.turn,
					ante: item.ante ?? undefined,
					hasScreenshot: false,
				});
			}
			const turnData = turnMap.get(item.turn)!;

			if (item.type === 'game_state') {
				// Store the entire game state JSON as a string
				turnData.state = item.blob;
			} else if (item.type === 'agent_reply') {
				// Parse the agent_reply JSON to extract action and reasoning
				try {
					const agentData = JSON.parse(item.blob);
					// Store action as formatted string
					turnData.action = JSON.stringify(agentData.action) + 
						(agentData.positions ? `\nPositions: ${JSON.stringify(agentData.positions)}` : '');
					turnData.reasoning = agentData.reasoning || 'No reasoning provided';
				} catch (e) {
					console.error(`  Error parsing agent_reply for turn ${item.turn}:`, e);
					turnData.action = item.blob;
					turnData.reasoning = 'Error parsing agent reply';
				}
			}
		}

		// Process screenshots
		for (const shot of screenShots) {
			if (!turnMap.has(shot.turn)) {
				turnMap.set(shot.turn, {
					turn: shot.turn,
					hasScreenshot: true,
				});
			} else {
				turnMap.get(shot.turn)!.hasScreenshot = true;
			}

			// Write screenshot as separate file
			let imageData = shot.screenshot_data;
			
			// Handle different data formats
			if (typeof imageData === 'string') {
				// Extract base64 data (remove data:image/png;base64, prefix if present)
				if (imageData.startsWith('data:')) {
					imageData = imageData.split(',')[1];
				}
				const screenshotPath = join(baseDir, `${shot.turn}.png`);
				await writeFile(screenshotPath, Buffer.from(imageData, 'base64'));
			} else if (Buffer.isBuffer(imageData)) {
				// Already a buffer, write directly
				const screenshotPath = join(baseDir, `${shot.turn}.png`);
				await writeFile(screenshotPath, imageData);
			}
		}

		// Write each turn's data as JSON
		const sortedTurns = Array.from(turnMap.entries()).sort((a, b) => a[0] - b[0]);
		const turnNumbers: number[] = [];

		for (const [turnNum, turnData] of sortedTurns) {
			turnNumbers.push(turnNum);
			const jsonPath = join(baseDir, `${turnNum}.json`);
			await writeFile(jsonPath, JSON.stringify(turnData, null, 2));
		}

		// Write metadata file for this run
		const outcome = run.won === 1 ? 'WON' : `Ante ${run.finalAnte ?? '?'}`;
		const metadata: RunMetadata = {
			agent: run.agent,
			seed: run.seed,
			runId: run.runId,
			outcome,
			turns: turnNumbers,
		};

		const metadataPath = join(baseDir, 'metadata.json');
		await writeFile(metadataPath, JSON.stringify(metadata, null, 2));

		runMetadataList.push(metadata);
		console.log(`  Exported ${turnNumbers.length} turns`);
	}

	// Write global index of all runs
	const indexPath = join(process.cwd(), 'public', 'turn-history', 'index.json');
	await writeFile(indexPath, JSON.stringify(runMetadataList, null, 2));

	sqliteDb.close();

	console.log(`\nExport complete! Exported ${runMetadataList.length} runs.`);
	console.log(`Files written to: public/turn-history/`);
}
