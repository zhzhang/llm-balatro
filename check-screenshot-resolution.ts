import { Database } from 'bun:sqlite';

const dbPath = 'game_history.db';

try {
  const db = new Database(dbPath, { readonly: true });

  // Get a few sample screenshots
  const screenshots = db.query(`
    SELECT id, run_id, turn, LENGTH(screenshot_data) as size, timestamp
    FROM screenshots 
    ORDER BY id 
    LIMIT 5
  `).all();

  console.log(`\nFound ${screenshots.length} sample screenshots:\n`);

  for (const screenshot of screenshots) {
    console.log(`Screenshot ID: ${screenshot.id}`);
    console.log(`  Run ID: ${screenshot.run_id}`);
    console.log(`  Turn: ${screenshot.turn}`);
    console.log(`  Size: ${screenshot.size} bytes`);
    console.log(`  Timestamp: ${screenshot.timestamp}`);
    
    // Get the actual blob data
    const result = db.query(`SELECT screenshot_data FROM screenshots WHERE id = ?`).get(screenshot.id);
    
    if (result && result.screenshot_data) {
      const blob = new Uint8Array(result.screenshot_data);
      
      // Check image format by looking at magic bytes
      let format = 'Unknown';
      if (blob[0] === 0x89 && blob[1] === 0x50 && blob[2] === 0x4E && blob[3] === 0x47) {
        format = 'PNG';
        
        // PNG format: width and height are at bytes 16-23
        // IHDR chunk contains dimensions at offset 16-19 (width) and 20-23 (height)
        const width = (blob[16] << 24) | (blob[17] << 16) | (blob[18] << 8) | blob[19];
        const height = (blob[20] << 24) | (blob[21] << 16) | (blob[22] << 8) | blob[23];
        console.log(`  Format: ${format}`);
        console.log(`  Resolution: ${width}x${height}`);
      } else if (blob[0] === 0xFF && blob[1] === 0xD8 && blob[2] === 0xFF) {
        format = 'JPEG';
        console.log(`  Format: ${format}`);
        
        // For JPEG, we need to parse through the segments to find SOF marker
        let i = 2;
        while (i < blob.length - 8) {
          if (blob[i] === 0xFF) {
            const marker = blob[i + 1];
            // SOF0, SOF1, SOF2 markers contain dimensions
            if (marker >= 0xC0 && marker <= 0xC3) {
              const height = (blob[i + 5] << 8) | blob[i + 6];
              const width = (blob[i + 7] << 8) | blob[i + 8];
              console.log(`  Resolution: ${width}x${height}`);
              break;
            }
            // Skip to next segment
            const segmentLength = (blob[i + 2] << 8) | blob[i + 3];
            i += 2 + segmentLength;
          } else {
            i++;
          }
        }
      } else {
        console.log(`  Format: ${format}`);
        console.log(`  First bytes: ${Array.from(blob.slice(0, 8)).map(b => '0x' + b.toString(16).padStart(2, '0')).join(' ')}`);
      }
    }
    console.log('');
  }

  db.close();
} catch (error) {
  console.error('Error:', error);
  process.exit(1);
}
