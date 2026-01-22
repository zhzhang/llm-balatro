import { Database } from 'bun:sqlite';
import sharp from 'sharp';

const dbPath = 'game_history.db';

async function optimizeScreenshots() {
  const db = new Database(dbPath);

  // Get total count
  const { count } = db.query('SELECT COUNT(*) as count FROM screenshots').get() as { count: number };
  console.log(`\nOptimizing ${count} screenshots...`);
  console.log('Converting from PNG (2048x1152) to WebP (1024x576)\n');

  // Process in batches
  const batchSize = 100;
  let processed = 0;
  let totalOriginalSize = 0;
  let totalNewSize = 0;

  const screenshots = db.query('SELECT id, screenshot_data FROM screenshots ORDER BY id').all();

  for (const screenshot of screenshots) {
    const originalBlob = new Uint8Array(screenshot.screenshot_data);
    totalOriginalSize += originalBlob.length;

    // Resize and convert to WebP
    const optimizedBuffer = await sharp(Buffer.from(originalBlob))
      .resize(1024, 576, { fit: 'cover' })
      .webp({ quality: 85, effort: 6 })
      .toBuffer();

    totalNewSize += optimizedBuffer.length;

    // Update the database
    db.query('UPDATE screenshots SET screenshot_data = ? WHERE id = ?')
      .run(optimizedBuffer, screenshot.id);

    processed++;

    if (processed % 10 === 0 || processed === count) {
      const progress = ((processed / count) * 100).toFixed(1);
      const avgOriginal = (totalOriginalSize / processed / 1024).toFixed(0);
      const avgNew = (totalNewSize / processed / 1024).toFixed(0);
      const reduction = (((totalOriginalSize - totalNewSize) / totalOriginalSize) * 100).toFixed(1);
      
      process.stdout.write(
        `\rProgress: ${processed}/${count} (${progress}%) | ` +
        `Avg: ${avgOriginal}KB → ${avgNew}KB | ` +
        `Reduction: ${reduction}%`
      );
    }
  }

  const finalReduction = (((totalOriginalSize - totalNewSize) / totalOriginalSize) * 100).toFixed(1);
  const originalSizeMB = (totalOriginalSize / 1024 / 1024).toFixed(2);
  const newSizeMB = (totalNewSize / 1024 / 1024).toFixed(2);
  const savedMB = (originalSizeMB - newSizeMB).toFixed(2);

  console.log('\n\n✅ Optimization complete!');
  console.log(`Original total size: ${originalSizeMB} MB`);
  console.log(`New total size: ${newSizeMB} MB`);
  console.log(`Space saved: ${savedMB} MB (${finalReduction}% reduction)`);

  db.close();
}

// Run the optimization
optimizeScreenshots().catch(error => {
  console.error('\n❌ Error:', error);
  process.exit(1);
});
