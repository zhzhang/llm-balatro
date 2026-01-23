import type { APIRoute } from 'astro';
import { db, turnHistory, screenshots, eq, and } from 'astro:db';

export const GET: APIRoute = async (context) => {
	const runId = context.url.searchParams.get('runId');
	console.log('Received runId:', runId, 'URL:', context.url.href);
	
	if (!runId) {
		return new Response(JSON.stringify({ error: 'Missing runId parameter' }), {
			status: 400,
			headers: {
				'Content-Type': 'application/json'
			}
		});
	}

	try {
		// Get all turn history for this run
		const history = await db
			.select()
			.from(turnHistory)
			.where(eq(turnHistory.runId, runId))
			.all();

		// Get all screenshots for this run
		const screenShots = await db
			.select()
			.from(screenshots)
			.where(eq(screenshots.runId, runId))
			.all();

		// Organize data by turn
		const turnMap = new Map<number, {
			turn: number;
			screenshot?: string;
			state?: string;
			action?: string;
			reasoning?: string;
			ante?: number;
		}>();

		// Process turn history
		for (const item of history) {
			if (!turnMap.has(item.turn)) {
				turnMap.set(item.turn, { turn: item.turn, ante: item.ante ?? undefined });
			}
			const turnData = turnMap.get(item.turn)!;
			
			if (item.type === 'state') {
				turnData.state = item.blob;
			} else if (item.type === 'action') {
				turnData.action = item.blob;
			} else if (item.type === 'reasoning') {
				turnData.reasoning = item.blob;
			}
		}

		// Add screenshots
		for (const shot of screenShots) {
			if (!turnMap.has(shot.turn)) {
				turnMap.set(shot.turn, { turn: shot.turn });
			}
			turnMap.get(shot.turn)!.screenshot = shot.screenshotData;
		}

		// Convert to sorted array
		const turns = Array.from(turnMap.values()).sort((a, b) => a.turn - b.turn);

		return new Response(JSON.stringify({ turns }), {
			status: 200,
			headers: {
				'Content-Type': 'application/json'
			}
		});
	} catch (error) {
		console.error('Error fetching turn history:', error);
		return new Response(JSON.stringify({ error: 'Failed to fetch turn history' }), {
			status: 500,
			headers: {
				'Content-Type': 'application/json'
			}
		});
	}
};
