import chalk from 'chalk';
import ora from 'ora';
import { readFileSync } from 'fs';
import { basename } from 'path';
import { VibecasterClient, ApiError } from '../client.js';
import { expandPlatforms } from '../util.js';

export function registerPost(program) {
  program
    .command('post <text>')
    .description('Post directly with your own text + optional media. No AI generation.')
    .option('-m, --media <path>', 'Path to image or video file')
    .option('-p, --platform <platform...>', 'Platform(s) to post to: twitter, linkedin, all', ['linkedin'])
    .action(async (text, options) => {
      const client = new VibecasterClient();
      client.ensureAuth();

      const platforms = expandPlatforms(options.platform);

      console.log(chalk.cyan.bold(`\n  Direct post → ${platforms.join(', ')}`));
      if (options.media) {
        console.log(`  Media: ${options.media}`);
      }

      // Build multipart form data
      const formData = new FormData();
      formData.append('text', text);
      formData.append('platforms', platforms.join(','));

      if (options.media) {
        const fileBuffer = readFileSync(options.media);
        const fileName = basename(options.media);
        let mimeType = 'application/octet-stream';
        if (options.media.endsWith('.mp4')) mimeType = 'video/mp4';
        else if (options.media.endsWith('.png')) mimeType = 'image/png';
        else if (options.media.endsWith('.jpg') || options.media.endsWith('.jpeg')) mimeType = 'image/jpeg';

        formData.append('media', new Blob([fileBuffer], { type: mimeType }), fileName);
      }

      let result;
      try {
        const response = await fetch(`${client.apiUrl}/cli/direct-post`, {
          method: 'POST',
          headers: { 'X-API-Key': client.apiKey },
          body: formData,
          signal: AbortSignal.timeout(30000),
        });

        if (response.status >= 400) {
          let detail;
          try {
            const json = await response.json();
            detail = json.detail || response.statusText;
          } catch {
            detail = response.statusText;
          }
          console.error(chalk.red(`  Error: ${detail}`));
          return;
        }
        result = await response.json();
      } catch (err) {
        if (err.name === 'TimeoutError') {
          console.error(chalk.red('  Error: Request timed out'));
        } else {
          console.error(chalk.red(`  Error: Could not connect to ${client.apiUrl}`));
        }
        return;
      }

      const jobId = result.job_id;
      if (!jobId) {
        console.error(chalk.red('  Error: No job ID returned'));
        return;
      }

      // Poll for completion
      const spinner = ora({ text: 'Posting...', color: 'cyan' }).start();
      const start = Date.now();

      while ((Date.now() - start) / 1000 < 300) {
        let job;
        try {
          job = await client.get(`/cli/jobs/${jobId}`);
        } catch {
          await new Promise((r) => setTimeout(r, 2000));
          continue;
        }

        const status = job.status || 'unknown';
        if (status === 'complete') {
          spinner.succeed('Done!');
          const jobResult = job.result || {};
          const posted = jobResult.posted || [];
          const errors = jobResult.errors || {};
          for (const p of posted) {
            console.log(`  ${chalk.green('✓')} Posted to ${p}`);
          }
          for (const [platform, error] of Object.entries(errors)) {
            console.log(`  ${chalk.red('✗')} ${platform}: ${error}`);
          }
          console.log();
          return;
        } else if (status === 'failed') {
          spinner.fail(`Failed: ${job.error || 'Unknown'}`);
          return;
        }

        spinner.text = 'Posting...';
        await new Promise((r) => setTimeout(r, 1500));
      }

      spinner.warn(`Timed out. Job ID: ${jobId}`);
    });
}
