import { defineDb, defineTable, column } from 'astro:db';

// https://astro.build/db/config
export default defineDb({
  tables: {
    gameRuns: defineTable({
      columns: {
        id: column.number({ primaryKey: true }),
        runId: column.text({ unique: true }),
        startedAt: column.text(),
        gamePlan: column.text({ optional: true }),
        reflection: column.text({ optional: true }),
        bestHand: column.number({ optional: true }),
        finalAnte: column.number({ optional: true }),
        finalRound: column.number({ optional: true }),
        endedAt: column.text({ optional: true }),
        seed: column.text({ optional: true }),
        agent: column.text({ optional: true }),
        completed: column.number({ default: 0 }),
        won: column.number({ default: 0 }),
      },
    }),
    screenshots: defineTable({
      columns: {
        id: column.number({ primaryKey: true }),
        runId: column.text(),
        turn: column.number(),
        screenshotData: column.text(), // Store as base64
        timestamp: column.text(),
      },
      indexes: {
        runTurnIdx: { on: ['runId', 'turn'], unique: true },
      },
    }),
    turnHistory: defineTable({
      columns: {
        id: column.number({ primaryKey: true }),
        runId: column.text(),
        turn: column.number(),
        type: column.text(),
        blob: column.text(),
        timestamp: column.text(),
        ante: column.number({ optional: true }),
        sentToGame: column.number({ default: 0 }),
        handResult: column.text({ optional: true }),
      },
      indexes: {
        runTurnTypeIdx: { on: ['runId', 'turn', 'type'], unique: true },
        runIdIdx: { on: ['runId'] },
      },
    }),
  },
});
