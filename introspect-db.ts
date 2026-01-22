import { Database } from 'bun:sqlite';

const dbPath = process.argv[2] || 'game_history.db';

try {
  const db = new Database(dbPath, { readonly: true });

  console.log(`\n=== Database Schema for: ${dbPath} ===\n`);

  // Get all tables
  const tables = db.query(`
    SELECT name FROM sqlite_master 
    WHERE type='table' 
    ORDER BY name
  `).all() as { name: string }[];

  console.log(`Found ${tables.length} table(s):\n`);

  for (const { name } of tables) {
    console.log(`\n📋 Table: ${name}`);
    console.log('─'.repeat(50));

    // Get table info (columns, types, etc.)
    const columns = db.query(`PRAGMA table_info(${name})`).all();
    
    console.log('\nColumns:');
    for (const col of columns) {
      const pk = col.pk ? ' [PRIMARY KEY]' : '';
      const notNull = col.notnull ? ' NOT NULL' : '';
      const defaultVal = col.dflt_value ? ` DEFAULT ${col.dflt_value}` : '';
      console.log(`  • ${col.name}: ${col.type}${pk}${notNull}${defaultVal}`);
    }

    // Get indexes
    const indexes = db.query(`PRAGMA index_list(${name})`).all();
    if (indexes.length > 0) {
      console.log('\nIndexes:');
      for (const idx of indexes) {
        const indexInfo = db.query(`PRAGMA index_info(${idx.name})`).all();
        const columns = indexInfo.map((info: any) => info.name).join(', ');
        const unique = idx.unique ? ' [UNIQUE]' : '';
        console.log(`  • ${idx.name}${unique}: (${columns})`);
      }
    }

    // Get foreign keys
    const foreignKeys = db.query(`PRAGMA foreign_key_list(${name})`).all();
    if (foreignKeys.length > 0) {
      console.log('\nForeign Keys:');
      for (const fk of foreignKeys) {
        console.log(`  • ${fk.from} → ${fk.table}.${fk.to}`);
      }
    }

    // Get row count
    const count = db.query(`SELECT COUNT(*) as count FROM ${name}`).get() as { count: number };
    console.log(`\nRow count: ${count.count}`);
  }

  db.close();
  console.log('\n' + '='.repeat(50) + '\n');
} catch (error) {
  console.error('Error reading database:', error);
  process.exit(1);
}
