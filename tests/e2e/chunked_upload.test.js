/**
 * Playwright E2E test for chunked video upload (files > 50MB)
 *
 * Prerequisites:
 * - cd tests/e2e && npm install playwright
 * - npx playwright install chromium
 * - npx playwright install-deps chromium
 *
 * Usage:
 * 1. Create a test account via the app or API
 * 2. Download a video > 50MB (e.g., Big Buck Bunny):
 *    curl -L -o /tmp/test_video.mp4 "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
 * 3. Update TEST_EMAIL and TEST_PASSWORD below
 * 4. Run: node tests/e2e/chunked_upload.test.js
 */

const { chromium } = require('playwright');

const TEST_EMAIL = 'your-test@email.com';
const TEST_PASSWORD = 'your-password';
const TEST_VIDEO_PATH = '/tmp/test_video.mp4';
const BASE_URL = 'https://vibecaster.ai';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  page.on('pageerror', err => console.log('PAGE ERROR:', err.message));

  try {
    // Login
    console.log('Logging in...');
    await page.goto(`${BASE_URL}/login`);
    await page.waitForLoadState('networkidle');
    await page.fill('input[type="email"]', TEST_EMAIL);
    await page.fill('input[type="password"]', TEST_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/', { timeout: 10000 });
    console.log('Logged in!');
    await page.waitForTimeout(2000);

    // Navigate to Video Post tab
    console.log('Clicking Video Post tab...');
    await page.click('button:has-text("Video Post")');
    await page.waitForTimeout(1000);

    // Find the drop zone and trigger file chooser
    const dropZone = page.locator('text=MP4, WebM, MOV').first();
    console.log('Opening file chooser...');

    const [fileChooser] = await Promise.all([
      page.waitForEvent('filechooser', { timeout: 5000 }),
      dropZone.click()
    ]);

    // Select the video file
    console.log('Selecting video file...');
    await fileChooser.setFiles(TEST_VIDEO_PATH);
    await page.waitForTimeout(3000);

    // Find the enabled Generate Posts button and click it
    const allGenButtons = await page.locator('button:has-text("Generate Posts")').all();
    for (const btn of allGenButtons) {
      const disabled = await btn.isDisabled();
      const visible = await btn.isVisible();

      if (visible && !disabled) {
        console.log('Clicking Generate Posts...');
        await btn.click();

        // Watch for chunk upload progress
        for (let i = 0; i < 300; i++) {
          await page.waitForTimeout(1000);
          const body = await page.textContent('body');

          // Check for chunk progress
          if (body.includes('Chunk ')) {
            const match = body.match(/Chunk \d+ of \d+/);
            if (match) console.log(`[${i}s] ${match[0]}`);
          }

          // Check for pattern error (the bug we're testing for)
          if (body.toLowerCase().includes('pattern')) {
            console.log(`[${i}s] *** PATTERN ERROR - TEST FAILED ***`);
            process.exit(1);
          }

          // Check for success - transcribing means upload completed
          if (body.includes('Transcrib')) {
            console.log(`[${i}s] SUCCESS - Upload complete, transcribing started!`);
            process.exit(0);
          }

          if (i % 30 === 0 && i > 0) console.log(`[${i}s] waiting...`);
        }

        console.log('Timeout waiting for upload to complete');
        process.exit(1);
      }
    }

    console.log('ERROR: Could not find enabled Generate Posts button');
    process.exit(1);

  } catch (err) {
    console.log('ERROR:', err.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
