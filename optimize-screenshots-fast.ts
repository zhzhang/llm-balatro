import { Database } from 'bun:sqlite';
import sharp from 'sharp';

const dbPath = 'game_history.db';
const BATCH_SIZE = 50; // Process and commit in batches

async function optimizeScreenshots() {
  const db = new Database(dbPath);

  // Get total count
  const { count } = db.query('SELECT COUNT(*) as count FROM screenshots').get() as { count: number };
  
  // Check how many are already optimized (WebP is much smaller)
  const avgSize = db.query('SELECT AVG(LENGTH(screenshot_data)) as avg FROM screenshots').get() as { avg: number };
  const alreadyOptimized = avgSize < 100000; // WebP images are ~75KB, PNG are ~2MB
  
  if (alreadyOptimized) {
    console.log(`\n✅ Screenshots already appear optimized (avg size: ${(avgSize / 1024).toFixed(0)}KB)`);
    db.close();
    return;
  }

  console.log(`\nOptimizing ${count} screenshots...`);
  console.log('Converting from PNG (2048x1152) to WebP (1024x576)\n');

  let processed = 0;
  let totalOriginalSize = 0;
  let totalNewSize = 0;

  // Use prepared statement for better performance
  const updateStmt = db.prepare('UPDATE screenshots SET screenshot_data = ? WHERE id = ?');

  // Process in batches with transactions
  let offset = 0;
  
  while (offset < count) {
    const screenshots = db.query(
      'SELECT id, screenshot_data FROM screenshots ORDER BY id LIMIT ? OFFSET ?'
    ).all(BATCH_SIZE, offset);

    if (screenshots.length === 0) break;

    // Begin transaction for this batch
    db.exec('BEGIN TRANSACTION');

    try {
      // Process all screenshots in this batch
      const optimizedData: Array<{ id: number; buffer: Buffer }> = [];
      
      for (const screenshot of screenshots) {
        const originalBlob = new Uint8Array(screenshot.screenshot_data);
        totalOriginalSize += originalBlob.length;

        // Resize and convert to WebP
        const optimizedBuffer = await sharp(Buffer.from(originalBlob))
          .resize(1024, 576, { fit: 'cover' })
          .webp({ quality: 85, effort: 6 })
          .toBuffer();

        totalNewSize += optimizedBuffer.length;
        optimizedData.push({ id: screenshot.id, buffer: optimizedBuffer });
      }

      // Update all in the batch
      for (const { id, buffer } of optimizedData) {
        updateStmt.run(buffer, id);
      }

      // Commit the transaction
      db.exec('COMMIT');

      processed += screenshots.length;
      offset += BATCH_SIZE;

      const progress = ((processed / count) * 100).toFixed(1);
      const avgOriginal = (totalOriginalSize / processed / 1024).toFixed(0);
      const avgNew = (totalNewSize / processed / 1024).toFixed(0);
      const reduction = (((totalOriginalSize - totalNewSize) / totalOriginalSize) * 100).toFixed(1);
      
      process.stdout.write(
        `\rProgress: ${processed}/${count} (${progress}%) | ` +
        `Avg: ${avgOriginal}KB → ${avgNew}KB | ` +
        `Reduction: ${reduction}%`
      );

    } catch (error) {
      // Rollback on error
      db.exec('ROLLBACK');
      throw error;
    }
  }

  const finalReduction = (((totalOriginalSize - totalNewSize) / totalOriginalSize) * 100).toFixed(1);
  const originalSizeMB = (totalOriginalSize / 1024 / 1024).toFixed(2);
  const newSizeMB = (totalNewSize / 1024 / 1024).toFixed(2);
  const savedMB = (parseFloat(originalSizeMB) - parseFloat(newSizeMB)).toFixed(2);

  console.log('\n\n✅ Optimization complete!');
  console.log(`Original total size: ${originalSizeMB} MB`);
  console.log(`New total size: ${newSizeMB} MB`);
  console.log(`Space saved: ${savedMB} MB (${finalReduction}% reduction)`);

  // Vacuum the database to reclaim space
  console.log('\n🗜️  Vacuuming database to reclaim space...');
  db.exec('VACUUM');
  console.log('✅ Done!');

  db.close();
}

// Run the optimization
optimizeScreenshots().catch(error => {
  console.error('\n❌ Error:', error);
  process.exit(1);
});
