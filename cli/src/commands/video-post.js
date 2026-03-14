import chalk from 'chalk';
import ora from 'ora';
import { readFileSync } from 'fs';
import { basename } from 'path';
import { VibecasterClient } from '../client.js';
import { expandPlatforms } from '../util.js';

export function registerVideoPost(program) {
  program
    .command('video-post <file>')
    .description('Transcribe video and generate platform posts (X, LinkedIn, YouTube)')
    .option('-p, --platform <platform...>', 'Platform(s) to post to: twitter, linkedin, youtube, all')
    .action(async (file, options) => {
      const client = new VibecasterClient();
      client.ensureAuth();

      const platforms = options.platform ? expandPlatforms(options.platform) : [];

      console.log(chalk.cyan.bold(`\n  Processing video: ${file}`));
      if (platforms.length > 0) {
        console.log(`  Will post to: ${platforms.join(', ')}`);
      } else {
        console.log(`  Preview only (use -p to post)`);
      }

      // Read the file
      let fileBuffer;
      try {
        fileBuffer = readFileSync(file);
      } catch (err) {
        console.error(chalk.red(`  Error: Could not read file: ${err.message}`));
        process.exitCode = 1;
        return;
      }

      const fileName = basename(file);
      let mimeType = 'video/mp4';
      const ext = file.toLowerCase().split('.').pop();
      if (ext === 'webm') mimeType = 'video/webm';
      else if (ext === 'mov') mimeType = 'video/quicktime';
      else if (ext === 'm4v') mimeType = 'video/x-m4v';

      // Submit job
      let result;
      try {
        const formData = new FormData();
        formData.append('file', new Blob([fileBuffer], { type: mimeType }), fileName);
        formData.append('platforms', platforms.join(','));

        const response = await fetch(`${client.apiUrl}/cli/video-post`, {
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
          process.exitCode = 1;
          return;
        }
        result = await response.json();
      } catch (err) {
        if (err.name === 'TimeoutError') {
          console.error(chalk.red('  Error: Request timed out'));
        } else {
          console.error(chalk.red(`  Error: Could not connect to ${client.apiUrl}`));
        }
        process.exitCode = 1;
        return;
      }

      const jobId = result.job_id;
      if (!jobId) {
        console.error(chalk.red('  Error: No job ID returned'));
        process.exitCode = 1;
        return;
      }

      // Poll for completion
      const statusLabels = {
        pending: 'Queued',
        uploading: 'Uploading video',
        transcribing: 'Transcribing audio',
        generating_posts: 'Generating posts',
        posting: 'Posting to platforms',
      };

      const spinner = ora({ text: 'Starting...', color: 'cyan' }).start();
      const start = Date.now();

      while ((Date.now() - start) / 1000 < 600) {
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
          const r = job.result || {};

          if (r.x_post) {
            console.log(chalk.cyan.bold('\n  [X/TWITTER]'));
            console.log(chalk.gray('  ' + '-'.repeat(50)));
            for (const line of r.x_post.split('\n')) {
              console.log(`  ${line}`);
            }
          }

          if (r.linkedin_post) {
            console.log(chalk.blue.bold('\n  [LINKEDIN]'));
            console.log(chalk.gray('  ' + '-'.repeat(50)));
            for (const line of r.linkedin_post.split('\n')) {
              console.log(`  ${line}`);
            }
          }

          if (r.youtube_title) {
            console.log(chalk.red.bold('\n  [YOUTUBE]'));
            console.log(chalk.gray('  ' + '-'.repeat(50)));
            console.log(`  Title: ${r.youtube_title}`);
            if (r.youtube_description) {
              console.log(`  Description: ${r.youtube_description.slice(0, 200)}...`);
            }
          }

          if (r.blog_post) {
            console.log(chalk.green.bold('\n  [BLOG POST]'));
            console.log(chalk.gray('  ' + '-'.repeat(50)));
            console.log(`  ${r.blog_post.slice(0, 500)}...`);
          }

          const posted = r.posted || [];
          const errors = r.errors || {};
          if (posted.length > 0) {
            console.log();
            for (const p of posted) {
              console.log(`  ${chalk.green('✓')} Posted to ${p}`);
            }
          }
          for (const [platform, error] of Object.entries(errors)) {
            console.log(`  ${chalk.red('✗')} ${platform}: ${error}`);
          }

          console.log();
          return;
        } else if (status === 'failed') {
          spinner.fail(`Failed: ${job.error || 'Unknown'}`);
          process.exitCode = 1;
          return;
        }

        spinner.text = `${statusLabels[status] || status}...`;
        await new Promise((r) => setTimeout(r, 2000));
      }

      spinner.warn(`Timed out. Job ID: ${jobId}`);
      console.log(`  Check later: vibecaster job ${jobId}`);
    });
}
